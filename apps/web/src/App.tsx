import { createBrowserRouter, RouterProvider } from "react-router-dom";
import Layout from "./components/Layout";
import Placeholder from "./components/Placeholder";

/**
 * Route table (spec 03 §2): `/` kanban, `/focus` dial, `/settings`.
 * Screens are placeholders until their own PR in the chain; the routes,
 * nav and dictionary are real so every later PR only adds components.
 */

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Placeholder titleKey="nav.tasks" /> },
      { path: "focus", element: <Placeholder titleKey="nav.focus" /> },
      { path: "settings", element: <Placeholder titleKey="nav.settings" /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
