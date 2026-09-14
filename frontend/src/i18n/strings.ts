/**
 * i18n string table — EN / বাংলা
 * Reviewed (not machine-translated) strings for Portion 11 foundation UI.
 * Layout must hold at 140% Bangla length (§6).
 */

export type Locale = "en" | "bn";

export const strings = {
  en: {
    // App / brand
    appName: "CohortOS",
    brandTag: "Coaching OS",

    // Auth
    authTitle: "Sign in",
    authSubtitle: "Enter your phone or email to receive a one-time code.",
    phoneOrEmail: "Phone or email",
    phonePlaceholder: "01XXXXXXXXX",
    emailPlaceholder: "you@centre.edu",
    tenantId: "Centre ID",
    tenantPlaceholder: "Your centre identifier",
    requestCode: "Send code",
    verifyTitle: "Enter code",
    verifySubtitle: "We sent a 6-digit code. It expires in a few minutes.",
    codeLabel: "One-time code",
    verify: "Verify & sign in",
    resend: "Resend code",
    signingIn: "Signing in…",
    sending: "Sending…",
    logout: "Sign out",

    // Shell
    navHome: "Home",
    navAttendance: "Attendance",
    navAdmissions: "Admissions",
    navFees: "Fees",
    navExams: "Exams",
    navVault: "Vault",
    navStaff: "Staff",
    navSettings: "Settings",
    navReview: "Review queue",
    navThreads: "Threads",
    navSolve: "Solve",
    navResults: "Results",
    navProfile: "Profile",
    workspace: "Workspace",
    notAvailableForRole: "Not available for your role",
    roleDeskNote: "Desk staff cannot access anti-leak controls.",

    // Sync pill (§4.4)
    syncOffline: "Offline · local",
    syncSyncing: "Syncing…",
    syncSynced: "Synced · {time} ago",
    syncConflict: "Sync conflict · review",
    offlineBannerBody: "Working from local data. Changes will sync when the connection returns.",
    justNow: "just now",
    minutesAgo: "{n} min",
    hoursAgo: "{n} h",

    // Buttons / common
    save: "Save",
    cancel: "Cancel",
    confirm: "Confirm",
    delete: "Delete",
    edit: "Edit",
    close: "Close",
    back: "Back",
    next: "Next",
    loading: "…",
    retry: "Retry",
    search: "Search",
    filter: "Filter",
    clear: "Clear",
    yes: "Yes",
    no: "No",

    // Status — attendance
    present: "Present",
    late: "Late",
    absent: "Absent",
    biometric: "Biometric",
    manual: "Manual",
    crossBatch: "Cross-batch",

    // Status — payment
    locked: "Locked",
    unpaid: "Unpaid",
    due: "Due",
    paid: "Paid",

    // Status — AI
    grounded: "Grounded",
    ungrounded: "Ungrounded",
    confidenceLow: "Low confidence",
    confidenceMedium: "Medium",
    confidenceHigh: "High",

    // Empty / loading
    emptyDefaultTitle: "Nothing here yet",
    emptyDefaultBody: "When there is data, it will appear in this list.",
    loadingView: "Loading…",

    // Errors
    networkError: "Network unavailable — working offline",
    rateLimited: "Too many requests. Try again in a moment.",
    unauthorized: "Session expired. Sign in again.",
    forbidden: "You do not have permission for this action.",
    notFound: "Not found.",
    genericError: "Something went wrong. Try again.",

    // Language
    langEn: "EN",
    langBn: "বাংলা",
    language: "Language",
  },

  bn: {
    // App / brand
    appName: "CohortOS",
    brandTag: "কোচিং ওএস",

    // Auth
    authTitle: "সাইন ইন",
    authSubtitle: "ওয়ান-টাইম কোড পেতে আপনার ফোন বা ইমেইল দিন।",
    phoneOrEmail: "ফোন বা ইমেইল",
    phonePlaceholder: "০১XXXXXXXXX",
    emailPlaceholder: "you@centre.edu",
    tenantId: "সেন্টার আইডি",
    tenantPlaceholder: "আপনার সেন্টারের পরিচয়",
    requestCode: "কোড পাঠান",
    verifyTitle: "কোড লিখুন",
    verifySubtitle: "আমরা ৬-অঙ্কের কোড পাঠিয়েছি। কয়েক মিনিটের মধ্যে মেয়াদ শেষ।",
    codeLabel: "ওয়ান-টাইম কোড",
    verify: "যাচাই ও সাইন ইন",
    resend: "কোড আবার পাঠান",
    signingIn: "সাইন ইন হচ্ছে…",
    sending: "পাঠানো হচ্ছে…",
    logout: "সাইন আউট",

    // Shell
    navHome: "হোম",
    navAttendance: "উপস্থিতি",
    navAdmissions: "ভর্তি",
    navFees: "ফি",
    navExams: "পরীক্ষা",
    navVault: "ভল্ট",
    navStaff: "স্টাফ",
    navSettings: "সেটিংস",
    navReview: "রিভিউ কিউ",
    navThreads: "থ্রেড",
    navSolve: "সলভ",
    navResults: "ফলাফল",
    navProfile: "প্রোফাইল",
    workspace: "ওয়ার্কস্পেস",
    notAvailableForRole: "আপনার ভূমিকার জন্য উপলব্ধ নয়",
    roleDeskNote: "ডেস্ক স্টাফ অ্যান্টি-লিক নিয়ন্ত্রণে প্রবেশ করতে পারে না।",

    // Sync pill
    syncOffline: "অফলাইন · স্থানীয়",
    syncSyncing: "সিঙ্ক হচ্ছে…",
    syncSynced: "সিঙ্কড · {time} আগে",
    offlineBannerBody: "স্থানীয় ডেটা থেকে কাজ চলছে। সংযোগ ফিরলে সিঙ্ক হবে।",
    syncConflict: "সিঙ্ক দ্বন্দ্ব · পর্যালোচনা",
    justNow: "এইমাত্র",
    minutesAgo: "{n} মিনিট",
    hoursAgo: "{n} ঘণ্টা",

    // Buttons / common
    save: "সংরক্ষণ",
    cancel: "বাতিল",
    confirm: "নিশ্চিত",
    delete: "মুছুন",
    edit: "সম্পাদনা",
    close: "বন্ধ",
    back: "পিছনে",
    next: "পরবর্তী",
    loading: "…",
    retry: "আবার চেষ্টা",
    search: "খুঁজুন",
    filter: "ফিল্টার",
    clear: "মুছুন",
    yes: "হ্যাঁ",
    no: "না",

    // Status — attendance
    present: "উপস্থিত",
    late: "দেরি",
    absent: "অনুপস্থিত",
    biometric: "বায়োমেট্রিক",
    manual: "ম্যানুয়াল",
    crossBatch: "ক্রস-ব্যাচ",

    // Status — payment
    locked: "লকড",
    unpaid: "অপরিশোধিত",
    due: "বকেয়া",
    paid: "পরিশোধিত",

    // Status — AI
    grounded: "গ্রাউন্ডেড",
    ungrounded: "আনগ্রাউন্ডেড",
    confidenceLow: "কম আত্মবিশ্বাস",
    confidenceMedium: "মাঝারি",
    confidenceHigh: "উচ্চ",

    // Empty / loading
    emptyDefaultTitle: "এখনো কিছু নেই",
    emptyDefaultBody: "ডেটা থাকলে এই তালিকায় দেখা যাবে।",
    loadingView: "লোড হচ্ছে…",

    // Errors
    networkError: "নেটওয়ার্ক নেই — অফলাইনে কাজ চলছে",
    rateLimited: "অনেক অনুরোধ। একটু পরে আবার চেষ্টা করুন।",
    unauthorized: "সেশন শেষ। আবার সাইন ইন করুন।",
    forbidden: "এই কাজের অনুমতি নেই।",
    notFound: "পাওয়া যায়নি।",
    genericError: "কিছু ভুল হয়েছে। আবার চেষ্টা করুন।",

    // Language
    langEn: "EN",
    langBn: "বাংলা",
    language: "ভাষা",
  },
} as const;

export type StringKey = keyof typeof strings.en;

export function t(locale: Locale, key: StringKey, vars?: Record<string, string | number>): string {
  let s: string = strings[locale][key] ?? strings.en[key] ?? key;
  if (vars) {
    Object.entries(vars).forEach(([k, v]) => {
      s = s.replace(`{${k}}`, String(v));
    });
  }
  return s;
}
