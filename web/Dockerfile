# The web app: Next.js, serving the pages and proxying /api/* to the API container.
FROM node:22-slim AS build
WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# The /api/* proxy target is fixed when the app is built.
ARG HR_API_URL=http://api:8010
ENV HR_API_URL=$HR_API_URL
RUN npm run build

FROM node:22-slim
WORKDIR /web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY --from=build /web/.next ./.next
COPY --from=build /web/public ./public
COPY --from=build /web/next.config.ts ./
EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
