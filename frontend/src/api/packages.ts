import { api } from './client';

import type {
  PackageInfo,
  PackageSnapshot,
} from '../types/api';

export function listPackages() {
  return api<{
    packages: PackageInfo[];
  }>('/packages');
}

export function getPackage(
  packageId: string,
) {
  return api<PackageInfo>(
    `/packages/${encodeURIComponent(packageId)}`,
  );
}

export function getActivePackage(
  domainId: string,
) {
  return api<PackageSnapshot | null>(
    `/packages/${encodeURIComponent(domainId)}/active`,
  );
}

export function getPackageVersion(
  packageId: string,
  version: string,
) {
  return api<PackageSnapshot>(
    `/packages/${encodeURIComponent(packageId)}/versions/${encodeURIComponent(version)}`,
  );
}