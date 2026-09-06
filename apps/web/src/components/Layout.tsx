/**
 * App shell: top navigation + routed content (spec 03 §2 routes).
 *
 * The foundation PR ships the wireframe only: kanban, dial and settings
 * screens arrive one PR each and plug into the routes below.
 */

import { NavLink, Outlet } from "react-router-dom";
import { t } from "../i18n/ru";

const LINK_CLASS =
  "rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground aria-[current=page]:bg-foreground aria-[current=page]:text-background";

export default function Layout() {
  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="app.shell">
      <header className="border-b bg-background/80 backdrop-blur">
        <nav
          className="mx-auto flex max-w-4xl items-center gap-1 px-4 py-3"
          aria-label={t("app.name")}
          data-testid="nav.root"
        >
          <span className="mr-4 text-lg font-bold" data-testid="nav.brand">
            {t("app.name")}
          </span>
          <NavLink to="/" end className={LINK_CLASS} data-testid="nav.tasks-link">
            {t("nav.tasks")}
          </NavLink>
          <NavLink to="/focus" className={LINK_CLASS} data-testid="nav.focus-link">
            {t("nav.focus")}
          </NavLink>
          <NavLink to="/settings" className={LINK_CLASS} data-testid="nav.settings-link">
            {t("nav.settings")}
          </NavLink>
        </nav>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
