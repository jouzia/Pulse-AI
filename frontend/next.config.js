/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // No image domains, no rewrites to the backend -- all backend calls go
  // through app/api/proxy, which attaches the API key server-side. See
  // that route's docstring and docs/architecture.md's dashboard section.
};

module.exports = nextConfig;
