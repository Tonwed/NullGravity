import { getRequestConfig } from "next-intl/server";
import { defaultLocale } from "./config";

export default getRequestConfig(async () => {
    // For static export, we use the default locale at build time
    // Client-side switching is handled by the LocaleProvider
    const locale = defaultLocale;

    return {
        locale,
        messages: (await import(`../messages/${locale}.json`)).default,
    };
});
