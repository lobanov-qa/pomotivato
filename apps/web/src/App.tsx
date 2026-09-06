import { createBrowserRouter, RouterProvider } from "react-router-dom";
import Layout from "./components/Layout";
import { KanbanScreen } from "./components/kanban/KanbanScreen";
import Placeholder from "./components/Placeholder";

/**
 * Route table (spec 03 §2): `/` kanban (live since 4/9... this PR),
 * `/focus` dial, `/settings`. The two later screens are placeholders until
 * their own PR; routes, nav and dictionary are already real.
 */

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <KanbanScreen /> },
      { path: "focus", element: <Placeholder titleKey="nav.focus" /> },
      { path: "settings", element: <Placeholder titleKey="nav.settings" /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
