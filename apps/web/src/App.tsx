import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { FocusScreen } from "./components/dial/FocusScreen";
import Layout from "./components/Layout";
import { KanbanScreen } from "./components/kanban/KanbanScreen";
import { SettingsScreen } from "./components/settings/SettingsScreen";
import { ThemeSync } from "./features/settings/hooks";

/**
 * Route table (spec 03 §2): `/` kanban, `/focus` dial, `/settings` —
 * all three screens are live. The dial is read-only for tasks by law.
 */

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <KanbanScreen /> },
      { path: "focus", element: <FocusScreen /> },
      { path: "settings", element: <SettingsScreen /> },
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
