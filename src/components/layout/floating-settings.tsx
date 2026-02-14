"use client";

import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import { Sun, Moon, Globe, Monitor, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuLabel,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { locales, localeNames, type Locale } from "@/i18n/config";
import { setUserLocaleSync } from "@/i18n/locale";
import { useEffect, useState } from "react";

export function FloatingSettings() {
    const t = useTranslations("settings");
    const { setTheme, resolvedTheme } = useTheme();
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
    }, []);

    function handleLocaleChange(locale: Locale) {
        setUserLocaleSync(locale);
    }

    return (
        <div className="fixed bottom-5 right-5 z-50">
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button
                        size="icon"
                        variant="outline"
                        className="h-9 w-9 rounded-full border-border bg-card shadow-sm hover:bg-accent"
                    >
                        <Settings2 className="h-4 w-4 text-muted-foreground" />
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" side="top" className="w-44 mb-1">
                    <DropdownMenuLabel className="text-[11px] text-muted-foreground font-normal uppercase tracking-wider">
                        {t("theme")}
                    </DropdownMenuLabel>
                    <DropdownMenuItem onClick={() => setTheme("light")} className="gap-2 text-[13px]">
                        <Sun className="h-3.5 w-3.5" />
                        {t("themeLight")}
                        {mounted && resolvedTheme === "light" && (
                            <span className="ml-auto text-[10px] text-muted-foreground">✓</span>
                        )}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => setTheme("dark")} className="gap-2 text-[13px]">
                        <Moon className="h-3.5 w-3.5" />
                        {t("themeDark")}
                        {mounted && resolvedTheme === "dark" && (
                            <span className="ml-auto text-[10px] text-muted-foreground">✓</span>
                        )}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => setTheme("system")} className="gap-2 text-[13px]">
                        <Monitor className="h-3.5 w-3.5" />
                        {t("themeSystem")}
                    </DropdownMenuItem>

                    <DropdownMenuSeparator />

                    <DropdownMenuLabel className="text-[11px] text-muted-foreground font-normal uppercase tracking-wider">
                        {t("language")}
                    </DropdownMenuLabel>
                    {locales.map((locale) => (
                        <DropdownMenuItem
                            key={locale}
                            onClick={() => handleLocaleChange(locale)}
                            className="gap-2 text-[13px]"
                        >
                            <Globe className="h-3.5 w-3.5" />
                            {localeNames[locale]}
                        </DropdownMenuItem>
                    ))}
                </DropdownMenuContent>
            </DropdownMenu>
        </div>
    );
}
