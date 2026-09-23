// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { ComponentProps, PropsWithChildren } from "react";
import { Provider } from "react-redux";

import { Notifications } from "@/Notifications/Notifications";

type AppProviderProps = PropsWithChildren<{
  store: ComponentProps<typeof Provider>["store"];
}>;

export const AppProvider = ({ children, store }: AppProviderProps) => (
  <Provider store={store}>
    {children}
    <Notifications />
  </Provider>
);
