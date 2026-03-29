FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 3000
CMD ["sh", "-c", "if [ ! -d node_modules ] || [ ! -x node_modules/.bin/next ]; then npm ci; fi; if [ \"${NODE_ENV:-development}\" = \"production\" ]; then npm run build && npm run start -- --hostname 0.0.0.0 --port 3000; else npm run dev -- --hostname 0.0.0.0 --port 3000; fi"]
