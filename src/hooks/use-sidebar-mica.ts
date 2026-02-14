"use client";

import { useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "nullgravity-sidebar-mica";

export function useSidebarMica() {
    const [mica, setMicaState] = useState(true);

    useEffect(() => {
        const stored = localStorage.getItem(STORAGE_KEY);
        const value = stored === null ? true : stored === "true";
        setMicaState(value);
        document.documentElement.setAttribute("data-sidebar-mica", String(value));
    }, []);

    const setMica = useCallback((enabled: boolean) => {
        setMicaState(enabled);
        localStorage.setItem(STORAGE_KEY, String(enabled));
        document.documentElement.setAttribute("data-sidebar-mica", String(enabled));
    }, []);

    return { mica, setMica };
}
