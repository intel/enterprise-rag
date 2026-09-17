// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  KeycloakService,
  useTokenRefresh,
} from "@intel-enterprise-rag-ui/auth";
import { AppProvider } from "@intel-enterprise-rag-ui/components";
import { ComponentProps, ReactNode } from "react";
import { Provider } from "react-redux";

type AppProps = {
  store: ComponentProps<typeof Provider>["store"];
  router: ReactNode;
  keycloakService: KeycloakService;
};

export const App = ({ store, router, keycloakService }: AppProps) => {
  useTokenRefresh(keycloakService);

  return <AppProvider store={store}>{router}</AppProvider>;
};
