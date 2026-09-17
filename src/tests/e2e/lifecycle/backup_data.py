#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The data the backup-restore scenario is judged on.

The three stages run as separate pytest sessions — before the backup, after the
backup, after the restore — so nothing is carried in memory between them. These
names are the whole handover: what the pre-backup stage creates is what the
post-restore stage looks for.

Created before the backup, so it must survive the restore:
"""

PRE_BACKUP_FILE = "test_pre_backup.txt"
PRE_BACKUP_QUESTION = (
    "What is the name of the cheese produced by Elvira Marqens from the village of Rulberton?"
)
PRE_BACKUP_ANSWER = "Trindlefoss."
# A conversation is listed under a name derived from its first question, which may
# be shortened, so it is looked up by a prefix rather than by the whole question.
PRE_BACKUP_HISTORY_MARKER = "What is the name of the cheese"
# The account lives in the realm, and the realm lives in the database whose volume
# the backup captures, so it comes back with the rest of the data.
PRE_BACKUP_USER = "backup-test"

# Created after the backup, so the restore must roll it back:
POST_BACKUP_FILE = "test_post_backup.txt"
POST_BACKUP_QUESTION = "How do voles affect the ecosystem near Gdansk Airport?"
POST_BACKUP_ANSWER = (
    "They serve as a crucial food source for various predators such as owls, "
    "foxes, and snakes, helping maintain the balance of the food web."
)
POST_BACKUP_HISTORY_MARKER = "How do voles affect"
# Created after the backup, like the document and the conversation above, and gone
# for the same reason once the restore replays the volume the realm sits on.
POST_BACKUP_USER = "post-backup-user"

# Asked after the restore: it can only be answered from the document and the
# embeddings the backup captured.
POST_RESTORE_QUESTION = "What unique product does Elvira Marqens craft in the village of Rulberton?"
POST_RESTORE_ANSWER_KEYWORD = "cheese"
