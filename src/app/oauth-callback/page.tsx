"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { getApiBase } from "@/lib/api";

export default function OAuthCallbackPage() {
  const searchParams = useSearchParams();

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const error = searchParams.get("error");

    if (error) {
      window.close();
      return;
    }

    if (code && state) {
      // Forward to backend callback
      const backendUrl = `${getApiBase()}/auth/google/callback?${searchParams.toString()}`;
      window.location.href = backendUrl;
    }
  }, [searchParams]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
        <p className="text-muted-foreground">Processing OAuth callback...</p>
      </div>
    </div>
  );
}
