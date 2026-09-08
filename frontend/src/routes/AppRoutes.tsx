import {
  Navigate,
  Route,
  Routes,
} from 'react-router-dom';

import { AppLayout } from '../layout/AppLayout';

import { LoginPage } from '../pages/LoginPage';

import { DomainsPage } from '../pages/domains/DomainsPage';
import { DomainCreatePage } from '../pages/domains/DomainCreatePage';

import { SourcesPage } from '../pages/sources/SourcesPage';
import { SourceCreatePage } from '../pages/sources/SourceCreatePage';
import { SourceDetailsPage } from '../pages/sources/SourceDetailsPage';

import { IngestionRunPage } from '../pages/ingestion/IngestionRunPage';

import { ProposalsPage } from '../pages/proposals/ProposalsPage';
import { ProposalReviewPage } from '../pages/proposals/ProposalReviewPage';

import { PackagesPage } from '../pages/packages/PackagesPage';
import { PackageDetailsPage } from '../pages/packages/PackageDetailsPage';
import { PackageVersionPage } from '../pages/packages/PackageVersionPage';

import { QueryPage } from '../pages/query/QueryPage';
import { QueryResultPage } from '../pages/query/QueryResultPage';

export function AppRoutes() {
  return (
    <Routes>
      {/* Public */}
      <Route
        path="/login"
        element={<LoginPage />}
      />

      {/* Protected application */}
      <Route element={<AppLayout />}>

        <Route
          path="/"
          element={
            <Navigate
              to="/domains"
              replace
            />
          }
        />

        {/* Domains */}
        <Route
          path="/domains"
          element={<DomainsPage />}
        />

        <Route
          path="/domains/new"
          element={<DomainCreatePage />}
        />

        {/* Sources */}
        <Route
          path="/sources"
          element={<SourcesPage />}
        />

        <Route
          path="/sources/new"
          element={<SourceCreatePage />}
        />

        <Route
          path="/sources/:sourceId"
          element={<SourceDetailsPage />}
        />

        {/* Ingestion */}
        <Route
          path="/ingestion-runs/:runId"
          element={<IngestionRunPage />}
        />

        {/* Knowledge */}
        <Route
          path="/proposals"
          element={<ProposalsPage />}
        />

        <Route
          path="/proposals/:proposalId"
          element={<ProposalReviewPage />}
        />

        {/* Packages */}
        <Route
          path="/packages"
          element={<PackagesPage />}
        />

        <Route
          path="/packages/:packageId"
          element={<PackageDetailsPage />}
        />

        <Route
          path="/packages/:packageId/versions/:version"
          element={<PackageVersionPage />}
        />

        {/* Query */}
        <Route
          path="/query"
          element={<QueryPage />}
        />

        <Route
          path="/query/result"
          element={<QueryResultPage />}
        />

        {/* Unknown */}
        <Route
          path="*"
          element={
            <Navigate
              to="/domains"
              replace
            />
          }
        />

      </Route>
    </Routes>
  );
}