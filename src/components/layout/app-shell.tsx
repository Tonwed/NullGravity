"use client";

import { AppSidebar } from "./app-sidebar";
import { FloatingSettings } from "./floating-settings";
import { type ReactNode } from "react";

export function AppShell({ children }: { children: ReactNode }) {
    return (
        <div className="sidebar-mica-bg flex h-screen overflow-hidden">
            <AppSidebar />
            <div className="flex flex-1 flex-col overflow-hidden p-2 pl-0">
                <div className="flex-1 overflow-hidden rounded-xl bg-background border border-border/100 flex flex-col">
                    <main className="flex-1 min-h-0 overflow-y-auto p-6">
                        {children}
                    </main>
                </div>
            </div>
            <FloatingSettings />
        </div>
    );
}
