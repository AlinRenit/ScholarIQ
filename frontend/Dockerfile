FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-slim AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN useradd --create-home --uid 10001 scholariq
COPY --from=build --chown=scholariq /app/.next/standalone ./
COPY --from=build --chown=scholariq /app/.next/static ./.next/static
USER scholariq
EXPOSE 3000
CMD ["node", "server.js"]
