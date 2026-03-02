
import os
import sys
import json
import platform
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger("fingerprint")

# ---------------------------------------------------------------------------
# Antigravity Network Fingerprint
# 逆向工程自 language_server_windows_x64.exe (Go binary, 160MB)
# ---------------------------------------------------------------------------
# 该模块负责精确构造与官方 Antigravity 完全一致的网络请求指纹。
#
# ⚠️ 重要架构说明：Antigravity 有两个独立的网络组件，header 风格完全不同：
#
# ┌─────────────────────────────────────────────────────────────────┐
# │ 1. main.js (Electron 主进程) — 账号登录/维护 (sync 流程)       │
# │    Headers:                                                     │
# │      Content-Type: application/json                             │
# │      User-Agent: antigravity/{ideVersion} {os}/{arch}           │
# │      Authorization: Bearer {token}                              │
# │    ❌ 不发送 x-goog-api-client / x-goog-request-params          │
# │    用于: loadCodeAssist, fetchAvailableModels, onboardUser 等    │
# │    代码位置: gemini_api.py → sandbox_post(), fetch_*()          │
# ├─────────────────────────────────────────────────────────────────┤
# │ 2. language_server (Go binary) — API 反代 (proxy 流程)         │
# │    Headers:                                                     │
# │      content-type: application/json                             │
# │      user-agent: windsurf/{version} {os}/{arch}                 │
# │      authorization: Bearer {token}                              │
# │      x-goog-api-client: gl-go/{go_ver} grpc-go/{grpc_ver}      │
# │      x-goog-request-params: project={project_id}               │
# │    用于: streamGenerateContent, generateContent 等 AI 请求      │
# │    代码位置: cloudcode_proxy.py, fingerprint.get_headers()      │
# └─────────────────────────────────────────────────────────────────┘
#
# 这两种流程必须严格隔离，混用会导致 403 PERMISSION_DENIED。
# ---------------------------------------------------------------------------


@dataclass
class AntigravityFingerprint:
    """保存从安装的 Antigravity 实例提取的指纹数据"""

    # User-Agent 组件
    ide_name: str = "antigravity"        # 抓包确认: User-Agent: antigravity/1.18.4
    ide_version: str = "1.18.4"          # 抓包确认: antigravity/1.18.4
    os_name: str = ""                     # 运行时检测: windows/darwin/linux
    arch: str = ""                        # 运行时检测: amd64/arm64

    # gRPC / Connect 版本 (逆向提取)
    grpc_go_version: str = "1.80.0-dev"  # Binary @37121087
    go_version: str = "1.27.0"           # Binary: go1.27-20260209-RC00
    connect_go_version: str = ""          # connect-go library

    @property
    def user_agent(self) -> str:
        """构造 User-Agent: windsurf/{ideVersion} {os}/{arch}
        
        逆向确认: 格式字符串 "%s/%s %s/%s" @36588143
        """
        return f"{self.ide_name}/{self.ide_version} {self.os_name}/{self.arch}"

    @property
    def x_goog_api_client(self) -> str:
        """构造 x-goog-api-client header
        
        Go gRPC libraries 自动添加此 header，格式:
        gl-go/{go_version} grpc-go/{grpc_version}
        """
        return f"gl-go/{self.go_version} grpc-go/{self.grpc_go_version}"

    def get_headers(self, access_token: str, project_id: Optional[str] = None) -> dict:
        """构造 language_server (Go gRPC) 风格的 HTTP 请求 headers
        
        ⚠️ 仅用于 API 反代 (proxy) 流程！
        账号登录/维护 (sync) 流程请直接构造 main.js 风格 headers，
        不要调用此方法，否则会导致 403。
        
        Header 名称全部小写 (HTTP/2 规范要求)
        
        逆向确认的必要 headers:
        - content-type: application/json
        - authorization: Bearer {token}
        - user-agent: windsurf/{version} {os}/{arch}
        - x-goog-api-client: gl-go/{go_ver} grpc-go/{grpc_ver}
        - x-goog-request-params: project={project_id} (可选)
        """
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {access_token}",
            "user-agent": self.user_agent,
            "x-goog-api-client": self.x_goog_api_client,
        }

        # 如果有 project_id，添加 Google 路由/审计 headers
        if project_id:
            headers["x-goog-request-params"] = f"project={project_id}"

        return headers


# ---------------------------------------------------------------------------
# 端点配置
# ---------------------------------------------------------------------------

# Gemini CLI 使用的 production 端点  
CODE_ASSIST_ENDPOINT = "https://cloudcode-pa.googleapis.com"
CODE_ASSIST_API_VERSION = "v1internal"

# Antigravity 端点路由
# isGcpTos=true  → production: cloudcode-pa.googleapis.com
# isGcpTos=false → daily:      daily-cloudcode-pa.googleapis.com
ANTIGRAVITY_ENDPOINT_DAILY = "https://daily-cloudcode-pa.googleapis.com"
ANTIGRAVITY_ENDPOINT_PROD = "https://cloudcode-pa.googleapis.com"


def get_antigravity_endpoint(is_gcp_tos: bool = False) -> str:
    """Select endpoint based on GCP ToS flag — mirrors official Antigravity."""
    return ANTIGRAVITY_ENDPOINT_PROD if is_gcp_tos else ANTIGRAVITY_ENDPOINT_DAILY


# ---------------------------------------------------------------------------
# v1internal API Methods (从 Binary 提取的完整清单)
# ---------------------------------------------------------------------------

V1INTERNAL_METHODS = {
    # 模型 & 内容生成
    "fetchAvailableModels",
    "generateContent",
    "streamGenerateContent",
    "generateCode",
    "completeCode",
    "generateChat",
    "streamGenerateChat",
    "countTokens",
    "transformCode",
    "tabChat",
    "internalAtomicAgenticChat",

    # 用户管理
    "fetchUserInfo",
    "onboardUser",
    "onboardUserBackgroundTasksA",
    "retrieveUserQuota",
    "setUserSettings",

    # 指标上报
    "recordCodeAssistMetrics",
    "recordClientEvent",
    "recordTrajectoryAnalytics",
    "recordSmartchoicesFeedbackA",

    # 配置
    "fetchAdminControls",
    "listExperiments",
    "listModelConfigsA",
    "getCodeAssistGlobalUserSetting",
    "setCodeAssistGlobalUserSetting",
    "loadCodeAssist",
    "fetchCodeCustomizationState",

    # 搜索 & 工具
    "searchSnippets",
    "rewriteUri",
    "checkUrlDenylist",
    "listAgents",
    "listRemoteRepositories",
    "listCloudAICompanionProjectsA",
    "migrateDatabaseCode",
}


# ---------------------------------------------------------------------------
# Google API Auth Scopes (从 Binary 提取)
# ---------------------------------------------------------------------------

GOOGLE_AUTH_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
]


# ---------------------------------------------------------------------------
# TLS Fingerprint (从 Binary 提取)
# Binary compiled with: go1.27-20260209-RC00 cl/867831283
# ---------------------------------------------------------------------------

GO_TLS_CIPHER_SUITES = {
    # TLS 1.3 (固定, 不可配置)
    "tls13": [
        "TLS_AES_128_GCM_SHA256",       # 0x1301 = 4865
        "TLS_AES_256_GCM_SHA384",       # 0x1302 = 4866
        "TLS_CHACHA20_POLY1305_SHA256", # 0x1303 = 4867
    ],
    # TLS 1.2 (默认顺序, 从 binary 确认)
    "tls12": [
        "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",  # 0xc02b = 49195
        "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",    # 0xc02f = 49199
        "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384",  # 0xc02c = 49196
        "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",    # 0xc030 = 49200
        "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256",  # 0xcca9 = 52393
        "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256",    # 0xcca8 = 52392
    ],
}

# JA3 指纹 — Go 1.27 crypto/tls 默认配置
# 格式: TLSVersion,CipherSuites,Extensions,EllipticCurves,ECPointFormats
#
# Binary 确认:
#   - Go 版本: go1.27-20260209-RC00
#   - ECH 支持: encrypted_client_hello (Yes)
#   - defaultCurvePreferences: X25519MLKEM768, X25519, P-256, P-384
#   - GREASE: No (Go 不使用 GREASE)
GO_TLS_JA3 = (
    "771,"                                  # TLS 1.2 (ClientHello version)
    "4865-4866-4867-"                       # TLS 1.3: AES_128_GCM, AES_256_GCM, CHACHA20
    "49195-49199-49196-49200-"              # ECDHE GCM
    "52393-52392,"                          # ECDHE CHACHA20
    "0-5-10-11-13-16-18-23-27-35-"          # SNI,status_req,groups,ec_pf,sig_algs,ALPN,SCT,EMS,cert_compress,ticket
    "43-45-51-17513-65281,"                 # supported_ver,psk_kex,key_share,ECH,renego_info
    "4588-29-23-24,"                        # X25519MLKEM768,X25519,P-256,P-384
    "0"                                     # uncompressed
)

# Akamai H2 指纹 (HTTP/2 SETTINGS frame)
# Go net/http2 默认 SETTINGS:
#   1:4096   (HEADER_TABLE_SIZE = 4096)
#   4:4194304 (INITIAL_WINDOW_SIZE = 4MB, Go 1.27 default)
# WINDOW_UPDATE: 1073741824 (1GB, Go connection-level window)
# PRIORITY: 0 (Go 不发送 PRIORITY frames)
# Pseudo-header order: :method, :scheme, :authority, :path (Go 默认)
GO_H2_AKAMAI = "1:4096;4:4194304|1073741824|0|m,s,a,p"


# ---------------------------------------------------------------------------
# 指纹初始化
# ---------------------------------------------------------------------------

def _detect_os() -> str:
    """检测操作系统名称 (Go format)"""
    system = platform.system()
    if system == "Windows":
        return "windows"
    elif system == "Darwin":
        return "darwin"
    else:
        return "linux"


def _detect_arch() -> str:
    """检测CPU架构 (Go format)"""
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "amd64"
    elif machine in ("aarch64", "arm64"):
        return "arm64"
    return machine


def create_fingerprint() -> AntigravityFingerprint:
    """创建并返回完整的 Antigravity 指纹对象
    
    版本号写死为 1.107.0 (当前安装的 Antigravity 版本)
    """
    fp = AntigravityFingerprint(
        ide_name="antigravity",
        ide_version="1.18.4",
        os_name=_detect_os(),
        arch=_detect_arch(),
        grpc_go_version="1.80.0-dev",
        go_version="1.27.0",
    )
    logger.info(f"Antigravity fingerprint initialized: UA='{fp.user_agent}'")
    return fp


# ---------------------------------------------------------------------------
# Global Singleton
# ---------------------------------------------------------------------------

_fingerprint: Optional[AntigravityFingerprint] = None


def get_fingerprint() -> AntigravityFingerprint:
    """获取全局指纹实例 (lazy singleton)"""
    global _fingerprint
    if _fingerprint is None:
        _fingerprint = create_fingerprint()
    return _fingerprint
