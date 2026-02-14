"use client";

import { defaultLocale, type Locale } from "./config";

const STORAGE_KEY = "nullgravity-locale";

export function getUserLocaleSync(): Locale {
    if (typeof window === "undefined") return defaultLocale;
    return (localStorage.getItem(STORAGE_KEY) as Locale) || defaultLocale;
}

export function setUserLocaleSync(locale: Locale): void {
    localStorage.setItem(STORAGE_KEY, locale);
    // Reload to apply new locale
    window.location.reload();
}
