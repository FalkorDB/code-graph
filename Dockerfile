# Use a Node.js base image
FROM node:20

# Set working directory
WORKDIR /app

# Copy package.json and install dependencies
COPY package*.json ./
RUN npm install

# Copy the rest of the application code
COPY . .

# Expose the port the frontend runs on
EXPOSE 3000

# Build nextJS
RUN npm run build

# Start the frontend
CMD ["npm", "start"]

