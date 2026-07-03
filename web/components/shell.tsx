"use client";

/** Authenticated app shell: top nav, org context, user menu.
 *  Hydrates /rbac/me once and passes it down via context. */
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { getMe, getToken, logout } from "@/lib/api";
import type { Me } from "@/lib/types";
import { ErrorBanner, Spinner } from "./ui";

interface MeContextValue {
  me: Me;
  orgId: string | null;
  setOrgId: (id: string) => void;
  refresh: () => Promise<void>;
}

const MeContext = createContext<MeContextValue | null>(null);

export function useMe(): MeContextValue {
  const ctx = useContext(MeContext);
  if (!ctx) throw new Error("useMe outside <Shell>");
  return ctx;
}

const NAV = [
  { href: "/dashboard", label: "Meetings" },
  { href: "/search", label: "Ask" },
  { href: "/admin/audit", label: "Audit", adminOnly: true },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [orgId, setOrgId] = useState<string | null>(null);

  const load = async () => {
    try {
      const data = await getMe();
      setMe(data);
      setOrgId((prev) => prev ?? data.orgs[0]?.org_id ?? null);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load profile");
    }
  };

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isAdmin = useMemo(
    () => me?.orgs.some((o) => o.org_id === orgId && o.role === "admin") ?? false,
    [me, orgId],
  );

  if (error)
    return (
      <div className="mx-auto max-w-lg pt-24 px-6">
        <ErrorBanner message={error} />
      </div>
    );
  if (!me) return <Spinner label="Loading workspace…" />;

  return (
    <MeContext.Provider value={{ me, orgId, setOrgId, refresh: load }}>
      <header className="sticky top-0 z-40 border-b border-edge bg-bg/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-6">
          <Link
            href="/dashboard"
            className="font-mono text-sm font-medium tracking-tight text-ink"
          >
            meet<span className="text-accent">graph</span>
          </Link>

          <nav className="flex items-center gap-1">
            {NAV.filter((n) => !n.adminOnly || isAdmin).map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                  pathname.startsWith(n.href)
                    ? "bg-raised text-ink"
                    : "text-muted hover:text-ink hover:bg-hover"
                }`}
              >
                {n.label}
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            {me.orgs.length > 0 && (
              <select
                aria-label="Organization"
                value={orgId ?? ""}
                onChange={(e) => setOrgId(e.target.value)}
                className="rounded-md border border-edge bg-raised px-2.5 py-1.5 text-sm text-ink-dim focus:outline-none focus:border-accent-dim"
              >
                {me.orgs.map((o) => (
                  <option key={o.org_id} value={o.org_id}>
                    {o.name ?? o.org_id.slice(0, 8)}
                  </option>
                ))}
              </select>
            )}
            <span className="hidden text-sm text-muted sm:block">
              {me.user.name ?? me.user.email}
            </span>
            <button
              onClick={logout}
              className="text-sm text-faint hover:text-ink transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
    </MeContext.Provider>
  );
}
