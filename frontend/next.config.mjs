/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    const base = process.env.NEXT_PUBLIC_API_BASE_URL
    if (!base) return []
    return [
      {
        source: "/api/:path*",
        destination: `${base}/api/:path*`,
      },
    ]
  },
}

export default nextConfig
