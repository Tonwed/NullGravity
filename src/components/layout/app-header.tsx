"use client";

import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import { Sun, Moon, Globe, Monitor } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { locales, localeNames, type Locale } from "@/i18n/config";
import { setUserLocaleSync } from "@/i18n/locale";

export function AppHeader() {
    const t = useTranslations("settings");
    const { setTheme, theme } = useTheme();

    function handleLocaleChange(locale: Locale) {
        setUserLocaleSync(locale);
    }

    return (
        <header className="flex h-14 items-center justify-end gap-2 border-b border-border bg-background/80 px-6 backdrop-blur-sm">
            {/* Language Switcher */}
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-9 w-9 text-muted-foreground hover:text-foreground"
                    >
                        <Globe className="h-4 w-4" />
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                    {locales.map((locale) => (
                        <DropdownMenuItem
                            key={locale}
                            onClick={() => handleLocaleChange(locale)}
                        >
                            {localeNames[locale]}
                        </DropdownMenuItem>
                    ))}
                </DropdownMenuContent>
            </DropdownMenu>

            {/* Theme Switcher */}
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-9 w-9 text-muted-foreground hover:text-foreground"
                    >
                        {theme === "dark" ? (
                            <Moon className="h-4 w-4" />
                        ) : theme === "light" ? (
                            <Sun className="h-4 w-4" />
                        ) : (
                            <Monitor className="h-4 w-4" />
                        )}
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => setTheme("light")}>
                        <Sun className="mr-2 h-4 w-4" />
                        {t("themeLight")}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => setTheme("dark")}>
                        <Moon className="mr-2 h-4 w-4" />
                        {t("themeDark")}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => setTheme("system")}>
                        <Monitor className="mr-2 h-4 w-4" />
                        {t("themeSystem")}
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>
        </header>
    );
}
