#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import subprocess # nosec B404
import os
import shutil
import allure
import logging
import glob
import json
from pathlib import Path


logger = logging.getLogger(__name__)

DEBUG_TOOL_TIMEOUT_SECONDS = 600  # 10 minutes
DEBUG_BUNDLE_PATTERN = "debug_bundle_*"
DEFAULT_KUBECONFIG = "/root/.kube/config"

# Expected subdirectories in debug_bundle
EXPECTED_SUBDIRS = ["kubectl_logs", "kubectl_get", "kubectl_getyaml", "kubectl_describe", "helm"]

# Expected files in debug_bundle root
EXPECTED_FILES = [
    "global_config_redacted.yaml",
    "config.erag_redacted.yaml",
    "config.inference_redacted.yaml",
    "SUMMARY.json",
    "debug_tool_execution.log",
]


def find_deployment_dir(start_path):
    """Recursively search upward from start_path to find the deployment directory."""
    current = Path(start_path).resolve()
    while current != current.parent:
        deployment_candidate = current / "deployment"
        if deployment_candidate.is_dir():
            logger.info(f"Found deployment directory: {deployment_candidate}")
            return deployment_candidate
        current = current.parent
    raise RuntimeError("Could not find 'deployment' directory in any parent directory")


def get_debug_bundle_dirs(deployment_dir):
    """Get all debug_bundle directories matching the pattern debug_bundle_*."""
    pattern = os.path.join(deployment_dir, DEBUG_BUNDLE_PATTERN)
    all_matches = glob.glob(pattern)
    return [m for m in all_matches if os.path.isdir(m)]


def get_kubeconfig_path():
    """Extract the kubeconfig path from the cfg dictionary."""
    kubeconfig = os.environ.get("KUBECONFIG")
    if not kubeconfig:
        return None
    if not os.path.isabs(kubeconfig):
        kubeconfig = os.path.abspath(kubeconfig)
    return kubeconfig


def verify_debug_bundle_structure(bundle_path):
    """Verify the debug_bundle directory structure and content."""
    logger.info(f"Verifying debug_bundle structure at: {bundle_path}")

    # Check expected subdirectories
    for subdir in EXPECTED_SUBDIRS:
        subdir_path = os.path.join(bundle_path, subdir)
        assert os.path.isdir(subdir_path), f"Expected subdirectory '{subdir}' not found"
        contents = os.listdir(subdir_path)
        assert len(contents) > 0, f"Subdirectory '{subdir}' is empty"
        logger.info(f"  [+] Subdirectory '{subdir}' verified with {len(contents)} items")

    # Check expected files
    for expected_file in EXPECTED_FILES:
        file_path = os.path.join(bundle_path, expected_file)
        assert os.path.isfile(file_path), f"Expected file '{expected_file}' not found"
        file_size = os.path.getsize(file_path)
        assert file_size > 0, f"Expected file '{expected_file}' is empty"
        logger.info(f"  [+] File '{expected_file}' verified ({file_size} bytes)")

    # Verify SUMMARY.json is valid JSON
    summary_path = os.path.join(bundle_path, "SUMMARY.json")
    with open(summary_path, "r") as f:
        summary_data = json.load(f)
    assert "collection_info" in summary_data, "SUMMARY.json missing 'collection_info'"
    assert "namespaces" in summary_data, "SUMMARY.json missing 'namespaces'"
    assert "total_pods" in summary_data, "SUMMARY.json missing 'total_pods'"
    assert "node_count" in summary_data, "SUMMARY.json missing 'node_count'"
    logger.info(f"  [+] SUMMARY.json valid with {len(summary_data.get('namespaces', []))} namespaces")

    # Verify helm_releases.txt has valid header and at least one release
    helm_releases_path = os.path.join(bundle_path, "helm", "helm_releases.txt")
    assert os.path.isfile(helm_releases_path), "helm/helm_releases.txt not found"
    with open(helm_releases_path, "r") as f:
        helm_lines = f.readlines()
    assert len(helm_lines) >= 2, "helm_releases.txt should contain header and at least one release"
    assert "NAMESPACE" in helm_lines[0], "helm_releases.txt missing expected header"
    logger.info(f"  [+] helm_releases.txt valid with {len(helm_lines) - 1} releases")


def handle_kubeconfig(kubeconfig_path):
    """Handle kubeconfig file: copy if needed, return whether it was copied."""
    if not kubeconfig_path:
        return False

    if os.path.exists(kubeconfig_path):
        logger.info(f"kubeconfig already exists at {kubeconfig_path}")
        return False

    if not os.path.exists(DEFAULT_KUBECONFIG):
        logger.warning(f"Default kubeconfig not found at {DEFAULT_KUBECONFIG}, skipping copy")
        return False

    logger.info(f"Copying kubeconfig from {DEFAULT_KUBECONFIG} to {kubeconfig_path}")
    os.makedirs(os.path.dirname(kubeconfig_path), exist_ok=True)
    shutil.copy(DEFAULT_KUBECONFIG, kubeconfig_path)
    return True


def run_debug_tool(deployment_dir, build_config_dir):
    """Execute debug_tool.py and verify it completes successfully."""
    os.chdir(deployment_dir)
    logger.info(f"Executing: python3 tools/debug_tool.py --config-dir {build_config_dir}")

    result = subprocess.run(
        ["python3", "tools/debug_tool.py", "--config-dir", build_config_dir],
        capture_output=True,
        text=True,
        timeout=DEBUG_TOOL_TIMEOUT_SECONDS
    )

    assert result.returncode == 0, (
        f"debug_tool.py failed with exit code {result.returncode}.\n"
        f"Stdout: {result.stdout}\n"
        f"Stderr: {result.stderr}"
    )


def verify_install_logs(bundle_path):
    """Verify the install_logs/ subdirectory exists and contains only non-empty files."""
    install_logs_dir = os.path.join(bundle_path, "install_logs")
    assert os.path.isdir(install_logs_dir), "Expected 'install_logs/' subdirectory not found in bundle"

    log_files = os.listdir(install_logs_dir)
    assert len(log_files) > 0, "'install_logs/' subdirectory is empty"

    for name in log_files:
        size = os.path.getsize(os.path.join(install_logs_dir, name))
        assert size > 0, f"Install log '{name}' is empty"
    logger.info(f"  [+] install_logs/ verified with {len(log_files)} non-empty log(s)")


def find_new_debug_bundle(deployment_dir, debug_bundles_before):
    """Return the path of the debug_bundle directory created since debug_bundles_before."""
    debug_bundles_after = get_debug_bundle_dirs(deployment_dir)
    new_bundles = [b for b in debug_bundles_after if b not in debug_bundles_before]
    assert len(new_bundles) > 0, f"No new debug_bundle directory created in {deployment_dir}"

    bundle_path = new_bundles[0]
    logger.info(f"Found new debug_bundle: {bundle_path}")
    return bundle_path


def verify_topology_preview(bundle_path):
    """Verify topology_preview_report.yaml is present (warn if missing, don't fail)."""
    topology_report_path = os.path.join(bundle_path, "topology_preview_report.yaml")
    if os.path.isfile(topology_report_path):
        logger.info(f"  [+] topology_preview_report.yaml found in bundle ({os.path.getsize(topology_report_path)} bytes)")
    else:
        logger.warning("  [!] topology_preview_report.yaml not found in debug bundle - topology preview may not have been generated yet")


def verify_archive_created(bundle_path):
    """Verify the compressed tar.gz archive for the bundle exists."""
    tar_gz_file = f"{bundle_path}.tar.gz"
    assert os.path.isfile(tar_gz_file), f"debug_bundle tar.gz file not found at {tar_gz_file}"
    logger.info(f"debug_bundle tar.gz file verified: {tar_gz_file}")


def verify_debug_bundle_created(deployment_dir, debug_bundles_before):
    """Verify a debug_bundle was created with all required content."""
    bundle_path = find_new_debug_bundle(deployment_dir, debug_bundles_before)

    verify_debug_bundle_structure(bundle_path)
    verify_topology_preview(bundle_path)
    verify_install_logs(bundle_path)
    verify_archive_created(bundle_path)

    return bundle_path


def cleanup_debug_bundle(deployment_dir, debug_bundles_before):
    """Clean up debug_bundle directories and tar.gz files created during test."""
    debug_bundles_final = get_debug_bundle_dirs(deployment_dir)
    for debug_bundle in debug_bundles_final:
        if debug_bundle not in debug_bundles_before:
            shutil.rmtree(debug_bundle)
            logger.info(f"Cleaned up debug_bundle directory: {debug_bundle}")

            tar_gz_file = f"{debug_bundle}.tar.gz"
            if os.path.isfile(tar_gz_file):
                os.remove(tar_gz_file)
                logger.info(f"Cleaned up tar.gz file: {tar_gz_file}")


def cleanup_kubeconfig(kubeconfig_path, was_copied):
    """Clean up kubeconfig file if it was copied during test."""
    if was_copied and kubeconfig_path and os.path.exists(kubeconfig_path):
        os.remove(kubeconfig_path)
        logger.info(f"Cleaned up kubeconfig file: {kubeconfig_path}")


@allure.testcase("IEASG-T522")
def test_debug_tool_execution(request):
    """Test that debug_tool.py runs successfully with the build config directory."""
    build_config_dir = os.path.abspath(request.config.getoption("--build-config-dir"))
    logger.info(f"Build config dir: {build_config_dir}")

    test_file = Path(__file__).resolve()
    deployment_dir = find_deployment_dir(test_file)
    original_dir = os.getcwd()

    # Record debug_bundles before test
    debug_bundles_before = get_debug_bundle_dirs(deployment_dir)
    logger.info(f"debug_bundles existing before test: {debug_bundles_before}")

    # Get kubeconfig path
    kubeconfig_path = get_kubeconfig_path()
    kubeconfig_was_copied = False

    try:
        # Setup
        kubeconfig_was_copied = handle_kubeconfig(kubeconfig_path)

        # Execute
        run_debug_tool(deployment_dir, build_config_dir)

        # Verify
        verify_debug_bundle_created(deployment_dir, debug_bundles_before)

    finally:
        # Cleanup
        cleanup_debug_bundle(deployment_dir, debug_bundles_before)
        cleanup_kubeconfig(kubeconfig_path, kubeconfig_was_copied)
        os.chdir(original_dir)
