# ── Build stage ─────────────────────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app
ARG REACT_APP_BACKEND_URL=https://api.leamss.com
ENV REACT_APP_BACKEND_URL=${REACT_APP_BACKEND_URL} \
    GENERATE_SOURCEMAP=false \
    CI=false
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund
COPY . .
RUN npm run build

# ── Runtime stage ───────────────────────────────────────────────────────────
FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
