FROM node:20-alpine
WORKDIR /app
ENV HOSTNAME=0.0.0.0 \
    PORT=3000
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]
