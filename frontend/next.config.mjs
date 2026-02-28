/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",

  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: "http://backend:8000/api/v1/:path*",
      },
    ];
  },

  async redirects() {
    return [
      {
        source: "/developer",
        destination: "/docs",
        permanent: false,
      },
      {
        source: "/developers",
        destination: "/docs",
        permanent: false,
      },
      {
        source: "/developer/:path*",
        destination: "/docs/:path*",
        permanent: false,
      },
      {
        source: "/developers/:path*",
        destination: "/docs/:path*",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
