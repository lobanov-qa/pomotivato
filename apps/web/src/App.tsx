import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { FocusScreen } from "./components/dial/FocusScreen";
import Layout from "./components/Layout";
import { KanbanScreen } from "./components/kanban/KanbanScreen";
import Placeholder from "./components/Placeholder";

/**
 * Route table (spec 03 §2): `/` kanban, `/focus` dial, `/settings`
 * (placeholder until its PR). The dial is read-only for tasks by law.
 */

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <KanbanScreen /> },
      { path: "focus", element: <FocusScreen /> },
      { path: "settings", element: <Placeholder titleKey="nav.settings" /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
