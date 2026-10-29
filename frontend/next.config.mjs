/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow external images for development (avatars, etc.)
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '**' },
    ],
  },
};

export default nextConfig;
