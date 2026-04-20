#!/usr/bin/env python3
# coding=utf-8

"""
Library core of ``repoconf``.
"""

import logging

import repoconf
import gitbolt
from repoconf.constants import REPOCONF_NAME

rclc = repoconf.repoconf_lc.clone_with_envs(f"{repoconf.REPOCONF_LOG_ENV}_CORE")
rclc_log = logging.getLogger(__name__)
rclc_logger = rclc.configure(rclc_log)


def main():
    git = gitbolt.get_git()
    print(git.version)
    rclc_logger.success(REPOCONF_NAME)


if __name__ == "__main__":
    main()
