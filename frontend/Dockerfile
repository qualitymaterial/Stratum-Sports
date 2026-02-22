# Build Stage
FROM node:20-alpine AS builder
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production Stage — uses Next.js standalone output for a minimal image
FROM node:20-alpine AS runner
WORKDIR /srv
ENV NODE_ENV=production

# Alpine busybox uses short flags; make creation idempotent across rebuilds.
RUN addgroup -S -g 1001 nodejs 2>/dev/null || true \
 && adduser -S -D -H -u 1001 -G nodejs nextjs 2>/dev/null || true

# Standalone bundle includes only the node_modules actually needed at runtime
COPY --from=builder /build/public ./public
COPY --from=builder --chown=nextjs:nodejs /build/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /build/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
