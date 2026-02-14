"use client";

import { NextIntlClientProvider } from "next-intl";
import { ThemeProvider } from "./theme-provider";
import { type ReactNode, useEffect, useState } from "react";
import { getUserLocaleSync } from "@/i18n/locale";
import { defaultLocale } from "@/i18n/config";
import { LogProvider } from "./log-provider";
import { SimpleToastProvider } from "@/components/ui/simple-toast";
import { WebSocketProvider } from "./websocket-provider";

// Import all messages statically for client-side switching
import enMessages from "@/messages/en.json";
import zhMessages from "@/messages/zh.json";

const allMessages: Record<string, Record<string, unknown>> = {
    en: enMessages,
    zh: zhMessages,
};

interface ProvidersProps {
    children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
    const [locale, setLocale] = useState(defaultLocale);

    useEffect(() => {
        setLocale(getUserLocaleSync());
        // Initialize sidebar mica attribute
        const mica = localStorage.getItem("nullgravity-sidebar-mica");
        document.documentElement.setAttribute(
            "data-sidebar-mica",
            mica === null ? "true" : mica
        );
    }, []);

    const messages = allMessages[locale] || allMessages[defaultLocale];

    return (
        <NextIntlClientProvider locale={locale} messages={messages}>
            <ThemeProvider
                attribute="class"
                defaultTheme="dark"
                enableSystem
                disableTransitionOnChange
            >
                <WebSocketProvider>
                    <LogProvider>
                        <SimpleToastProvider>
                            {children}
                        </SimpleToastProvider>
                    </LogProvider>
                </WebSocketProvider>
            </ThemeProvider>
        </NextIntlClientProvider>
    );
}
