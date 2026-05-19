# ============================================================================
# Frontend Next.js (v0-secure-point-dashboard-design) - image production
# ============================================================================

# ---- Builder ----
FROM node:22-alpine AS builder
WORKDIR /app

# package-lock is preferred because the pnpm lockfile can lag package.json.
COPY package.json package-lock.json* pnpm-lock.yaml* yarn.lock* ./
RUN if [ -f package-lock.json ]; then \
      npm ci --legacy-peer-deps; \
    elif [ -f pnpm-lock.yaml ]; then \
      corepack enable && pnpm install --frozen-lockfile; \
    elif [ -f yarn.lock ]; then \
      yarn install --frozen-lockfile; \
    else \
      npm install --legacy-peer-deps; \
    fi

COPY . .

ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_EMPLOYEE_API_BASE_URL
ARG NEXT_PUBLIC_BETA_MODE=1
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_EMPLOYEE_API_BASE_URL=$NEXT_PUBLIC_EMPLOYEE_API_BASE_URL
ENV NEXT_PUBLIC_BETA_MODE=$NEXT_PUBLIC_BETA_MODE
ENV NODE_ENV=production

RUN npm run build

# ---- Runtime ----
FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000

RUN addgroup -S nodejs && adduser -S nextjs -G nodejs

COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.* ./

RUN chown -R nextjs:nodejs /app
USER nextjs

EXPOSE 3000
CMD ["npm", "run", "start"]
