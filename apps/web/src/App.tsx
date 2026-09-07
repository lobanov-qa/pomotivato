import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { FocusScreen } from "./components/dial/FocusScreen";
import Layout from "./components/Layout";
import { KanbanScreen } from "./components/kanban/KanbanScreen";
import { SettingsScreen } from "./components/settings/SettingsScreen";
import { StatsScreen } from "./components/stats/StatsScreen";
import { ThemeSync } from "./features/settings/hooks";
import { WeekScreen } from "./components/week/WeekScreen";

/**
 * Route table (spec 03 §2 + spec 04 §2): `/` kanban, `/focus` dial,
 * `/settings`, `/stats` dashboard, `/week` browser — all live, all
 * read-only where the screen-law says so (stats/week never edit).
 */

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <KanbanScreen /> },
      { path: "focus", element: <FocusScreen /> },
      { path: "settings", element: <SettingsScreen /> },
      { path: "stats", element: <StatsScreen /> },
      { path: "week", element: <WeekScreen /> },
    ],
  },
]);

export default function App() {
  return (
    <>
      <ThemeSync />
      <RouterProvider router={router} />
    </>
  );
}
