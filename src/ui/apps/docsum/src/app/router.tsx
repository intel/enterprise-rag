// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  AccessGuard,
  AdminPanelGuard,
  keycloakService,
} from "@intel-enterprise-rag-ui/auth";
import {
  LoadingFallback,
  useColorScheme,
} from "@intel-enterprise-rag-ui/components";
import { RootLayout } from "@intel-enterprise-rag-ui/layouts";
import { lazy, Suspense } from "react";
import {
  createBrowserRouter,
  Navigate,
  RouterProvider,
} from "react-router-dom";

import ErrorRoute from "@/app/routes/error/ErrorRoute";
import UnauthorizedRoute from "@/app/routes/unauthorized/UnauthorizedRoute";
import { paths } from "@/config/paths";
import { getDocSumAppEnv } from "@/utils";

const DocSumRoute = lazy(() => import("@/app/routes/docsum/DocSumRoute"));
const AdminPanelRoute = lazy(
  () => import("@/app/routes/admin-panel/AdminPanelRoute"),
);

const router = createBrowserRouter([
  {
    path: paths.root,
    element: <Navigate to={`${paths.docsum}/paste-text`} replace />,
    errorElement: <ErrorRoute />,
  },
  {
    path: paths.unauthorized,
    element: <UnauthorizedRoute />,
  },
  {
    element: (
      <AccessGuard
        userRole={getDocSumAppEnv("USER_RESOURCE_ROLE")}
        keycloakService={keycloakService}
      >
        <RootLayout />
      </AccessGuard>
    ),
    children: [
      {
        path: `${paths.docsum}/*`,
        element: (
          <Suspense fallback={<LoadingFallback />}>
            <DocSumRoute />
          </Suspense>
        ),
      },
      {
        path: `${paths.adminPanel}/*`,
        element: (
          <AdminPanelGuard
            redirectTo={paths.docsum}
            keycloakService={keycloakService}
          >
            <Suspense fallback={<LoadingFallback />}>
              <AdminPanelRoute />
            </Suspense>
          </AdminPanelGuard>
        ),
      },
      { path: "*", element: <ErrorRoute /> },
    ],
  },
]);

const AppRouter = () => {
  // useColorScheme hook used here to provide color scheme for the app and LoadingFallback component
  useColorScheme();

  return <RouterProvider router={router} />;
};

export default AppRouter;
