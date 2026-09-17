"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Overview" },
  { href: "/events", label: "Events" },
  { href: "/dead-letter", label: "Dead letter" },
  { href: "/observability", label: "Observability" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className="flex h-screen w-56 flex-shrink-0 flex-col border-r border-border bg-surface"
    >
      <div className="border-b border-border px-4 py-4">
        <p className="text-sm font-medium text-text-primary">Pulse</p>
        <p className="text-xs text-text-tertiary">Operations console</p>
      </div>
      <ul className="flex-1 py-2">
        {NAV_ITEMS.map((item) => {
          const active =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`block border-l-2 px-4 py-2 text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${
                  active
                    ? "border-accent bg-accent-dim text-text-primary"
                    : "border-transparent text-text-secondary hover:text-text-primary"
                }`}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
