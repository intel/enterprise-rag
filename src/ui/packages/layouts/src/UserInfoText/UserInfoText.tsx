// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./UserInfoText.css";

interface UserInfoTextProps {
  /** User information to display (e.g. username or email) */
  text: string;
}

/**
 * Displays a line of user information (username, email, ...) in the side panel footer.
 */
export const UserInfoText = ({ text }: UserInfoTextProps) => (
  <p className="user-info__text">{text}</p>
);
