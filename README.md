<div align="center">

# NullGravity

![License](https://img.shields.io/badge/license-CC%20BY--NC--SA%204.0-blue?style=flat-square)
![Status](https://img.shields.io/badge/status-active-success?style=flat-square)
![Tauri](https://img.shields.io/badge/Tauri-blue?style=flat-square&logo=tauri)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react)
![Next.js](https://img.shields.io/badge/Next.js-16-black?style=flat-square&logo=next.js)
![Python](https://img.shields.io/badge/Python-3.12-yellow?style=flat-square&logo=python)

**Defy Expectations.**

NullGravity is a comprehensive system for managing AI service accounts and proxy configurations. It provides a unified dashboard to monitor account health, handle Google OAuth authentications, and seamlessly integrate with Antigravity.

[English](./README.md) | [简体中文](./README_zh.md)

</div>

---

## 🚀 Overview

## 🚀 Overview

NullGravity combines web and desktop technologies to provide a unified experience.

### Key Features
- **Account Management**: Centralized control for AI accounts with device fingerprint isolation and Google OAuth support.
- **Proxy System**: Built-in configurable upstream proxy settings to ensure seamless network connectivity.
- **Antigravity Integration**: Auto-detection, launch management, and cache cleaning for external Antigravity instances.
- **Real-time Monitoring**: Visual dashboard displaying request logs, success rates, and account quotas.

<div align="center">
  <img src="image_1" alt="Software Screenshot 1" width="45%" />
  <img src="image_2" alt="Software Screenshot 2" width="45%" />
</div>
---

## 🛠️ Tech Stack

The project is built using:

| Domain | Technologies |
| :--- | :--- |
| **Desktop** | [Tauri v2](https://tauri.app/) |
| **Frontend** | [React 19](https://react.dev/), [Next.js 16](https://nextjs.org/), [Vite](https://vitejs.dev/) |
| **Styling** | [Tailwind CSS v4](https://tailwindcss.com/), [Shadcn UI](https://ui.shadcn.com/), [Ant Design](https://ant.design/) |
| **Backend** | [Python](https://www.python.org/) |
| **AI** | [Google Gemini](https://deepmind.google/technologies/gemini/) |

---

## 💻 Getting Started

This project is organized as a workspace. Each component can be run independently.

### Prerequisites
- **Node.js**: v20+ (Recommended)

- **Python**: 3.10+

### Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-username/NullGravity.git
    cd NullGravity
    ```

2.  **Navigate to a project** (e.g., the Core App):
    ```bash
    cd app
    npm install
    ```

3.  **Run Development Server**:
    ```bash
    npm run dev
    # or for Tauri
    npm run tauri dev
    ```

This project references [lbjlaq/Antigravity-Manager](https://github.com/lbjlaq/Antigravity-Manager).
---

## 📄 License

This project is licensed under the **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)**.

---

<div align="center">
  <sub>Built with ❤️ by the NullGravity Team</sub>
</div>
