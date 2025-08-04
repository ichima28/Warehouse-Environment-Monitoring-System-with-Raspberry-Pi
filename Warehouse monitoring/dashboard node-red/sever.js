const express = require('express');
const fs = require('fs');
const { parse } = require('csv-parse');
const path = require('path');
const cors = require('cors');
const csvWriter = require('csv-write-stream');
const os = require('os');

const app = express();
const port = 3000;
const LOG_DIR = path.join(__dirname, '../logs'); // Logs directory at the same level as api
const CONFIG_DIR = path.join(__dirname, '../config');
const CONFIG_FILE = path.join(CONFIG_DIR, 'config.txt');

// Giá trị cấu hình mặc định
const DEFAULT_CONFIG = {
    TEMP_MAX: 32.0,
    TEMP_MIN: 20.0,
    HUMI_MIN: 40.0,
    HUMI_MAX: 70.0,
    pi_name: os.hostname() // Giá trị mặc định cho pi_name là hostname
};

// Middleware
app.use(cors()); // Enable CORS for Node-RED
app.use(express.json()); // Parse JSON bodies for POST requests
app.use((req, res, next) => {
    res.setHeader('X-Content-Type-Options', 'nosniff'); // Basic security headers
    res.setHeader('X-Frame-Options', 'DENY');
    next();
});

// Debug: Log logs directory path
console.log(`[DEBUG] LOG_DIR path: ${LOG_DIR}`);
console.log(`[DEBUG] CONFIG_DIR path: ${CONFIG_DIR}`);

// Create logs directory if it doesn't exist
try {
    if (!fs.existsSync(LOG_DIR)) {
        console.log(`[DEBUG] Creating logs directory: ${LOG_DIR}`);
        fs.mkdirSync(LOG_DIR, { recursive: true });
    } else {
        console.log(`[DEBUG] Logs directory already exists: ${LOG_DIR}`);
    }
} catch (err) {
    console.error(`[ERROR] Failed to create/check logs directory: ${err.message}`);
}

try {
    if (!fs.existsSync(CONFIG_DIR)) {
        console.log(`[DEBUG] Creating config directory: ${CONFIG_DIR}`);
        fs.mkdirSync(CONFIG_DIR, { recursive: true });
    } else {
        console.log(`[DEBUG] Config directory already exists: ${CONFIG_DIR}`);
    }
} catch (err) {
    console.error(`[ERROR] Failed to create/check config directory: ${err.message}`);
}

// API to get config
app.get('/config', (req, res) => {
    console.log(`[DEBUG] Received request for /config`);
    try {
        if (!fs.existsSync(CONFIG_FILE)) {
            console.log(`[DEBUG] Config file not found, creating with default values: ${CONFIG_FILE}`);
            fs.writeFileSync(CONFIG_FILE, 
                Object.entries(DEFAULT_CONFIG)
                    .map(([key, value]) => `${key}=${value}`)
                    .join('\n')
            );
        }

        const config = {};
        const data = fs.readFileSync(CONFIG_FILE, 'utf8');
        data.split('\n').forEach(line => {
            line = line.trim();
            if (line && line.includes('=')) {
                const [key, value] = line.split('=', 2);
                const trimmedKey = key.trim();
                const trimmedValue = value.trim();
                if (trimmedKey in DEFAULT_CONFIG) {
                    config[trimmedKey] = trimmedKey === 'pi_name' ? trimmedValue : parseFloat(trimmedValue);
                }
            }
        });

        console.log(`[DEBUG] Loaded config: ${JSON.stringify(config)}`);
        res.json(config);
    } catch (error) {
        console.error(`[ERROR] Error reading config file ${CONFIG_FILE}: ${error.message}`);
        res.status(500).json({ error: `Error reading config: ${error.message}` });
    }
});

// API to update config
app.post('/config', (req, res) => {
    console.log(`[DEBUG] Received POST request for /config with body: ${JSON.stringify(req.body)}`);
    const { TEMP_MAX, TEMP_MIN, HUMI_MIN, HUMI_MAX } = req.body;

    // Load current config to preserve pi_name
    let currentConfig = { ...DEFAULT_CONFIG };
    if (fs.existsSync(CONFIG_FILE)) {
        const data = fs.readFileSync(CONFIG_FILE, 'utf8');
        data.split('\n').forEach(line => {
            line = line.trim();
            if (line && line.includes('=')) {
                const [key, value] = line.split('=', 2);
                const trimmedKey = key.trim();
                const trimmedValue = value.trim();
                if (trimmedKey in DEFAULT_CONFIG) {
                    currentConfig[trimmedKey] = trimmedKey === 'pi_name' ? trimmedValue : parseFloat(trimmedValue);
                }
            }
        });
    }

    // Validate input
    const newConfig = { ...currentConfig };
    for (const key of ['TEMP_MAX', 'TEMP_MIN', 'HUMI_MIN', 'HUMI_MAX']) {
        if (req.body[key] !== undefined) {
            const value = parseFloat(req.body[key]);
            if (isNaN(value) || value < 0) {
                console.log(`[ERROR] Invalid ${key}: ${req.body[key]}. Must be a non-negative number.`);
                return res.status(400).json({ error: `Invalid ${key}: Must be a non-negative number.` });
            }
            newConfig[key] = value;
        }
    }

    // Check logical constraints
    if (newConfig.TEMP_MAX <= newConfig.TEMP_MIN) {
        console.log(`[ERROR] TEMP_MAX must be greater than TEMP_MIN`);
        return res.status(400).json({ error: 'TEMP_MAX must be greater than TEMP_MIN.' });
    }
    if (newConfig.HUMI_MAX <= newConfig.HUMI_MIN) {
        console.log(`[ERROR] HUMI_MAX must be greater than HUMI_MIN`);
        return res.status(400).json({ error: 'HUMI_MAX must be greater than HUMI_MIN.' });
    }

    // Write to config file
    try {
        fs.writeFileSync(CONFIG_FILE, 
            Object.entries(newConfig)
                .map(([key, value]) => `${key}=${value}`)
                .join('\n')
        );
        console.log(`[DEBUG] Successfully updated config file: ${CONFIG_FILE}`);
        res.json({ message: 'Config updated successfully', config: newConfig });
    } catch (error) {
        console.error(`[ERROR] Error writing to config file ${CONFIG_FILE}: ${error.message}`);
        res.status(500).json({ error: `Error writing config: ${error.message}` });
    }
});

// API to get data by date (e.g., /data?date=2025-08-01&startTime=2025-08-01T00:00:00&endTime=2025-08-01T23:59:59)
app.get('/data', (req, res) => {
    console.log(`[DEBUG] Received request for /data with query: ${JSON.stringify(req.query)}`);
    const { date, startTime, endTime } = req.query;

    if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
        console.log(`[ERROR] Invalid date format: ${date}`);
        return res.status(400).json({ error: 'Invalid date format. Use YYYY-MM-DD.' });
    }

    const csvPath = path.join(LOG_DIR, `${date}.csv`);
    console.log(`[DEBUG] Attempting to read CSV file: ${csvPath}`);

    if (!fs.existsSync(csvPath)) {
        console.log(`[ERROR] CSV file not found: ${csvPath}`);
        return res.status(404).json({ error: `No data found for ${date}.` });
    }

    const results = [];
    fs.createReadStream(csvPath)
        .pipe(parse({ columns: true, trim: true }))
        .on('data', (row) => {
            console.log(`[DEBUG] Parsed CSV row: ${JSON.stringify(row)}`);
            // Filter by startTime and endTime if provided
            if (startTime && endTime) {
                const rowTime = new Date(row.timestamp).getTime();
                const start = new Date(startTime).getTime();
                const end = new Date(endTime).getTime();
                if (rowTime < start || rowTime > end) return;
            }
            results.push({
                timestamp: row.timestamp,
                temperature_c: parseFloat(row.temperature_c),
                humidity_pct: parseFloat(row.humidity_pct),
                temp_avg_300s: parseFloat(row.temp_avg_300s),
                humi_avg_300s: parseFloat(row.humi_avg_300s),
                temp_min_300s: parseFloat(row.temp_min_300s),
                temp_max_300s: parseFloat(row.temp_max_300s),
                humi_min_300s: parseFloat(row.humi_min_300s),
                humi_max_300s: parseFloat(row.humi_max_300s)
            });
        })
        .on('end', () => {
            console.log(`[DEBUG] Finished reading CSV, sending ${results.length} rows`);
            res.json(results);
        })
        .on('error', (error) => {
            console.error(`[ERROR] Error reading CSV file ${csvPath}: ${error.message}`);
            res.status(500).json({ error: `Error reading CSV: ${error.message}` });
        });
});

// API to post data (e.g., from Node-RED instead of Python script)
app.post('/data', (req, res) => {
    console.log(`[DEBUG] Received POST request for /data with body: ${JSON.stringify(req.body)}`);
    const { timestamp, temperature_c, humidity_pct, temp_avg_300s, humi_avg_300s, temp_min_300s, temp_max_300s, humi_min_300s, humi_max_300s } = req.body;

    if (!timestamp || !temperature_c || !humidity_pct) {
        console.log(`[ERROR] Missing required fields in POST data`);
        return res.status(400).json({ error: 'Missing required fields: timestamp, temperature_c, humidity_pct.' });
    }

    const date = timestamp.split('T')[0];
    const csvPath = path.join(LOG_DIR, `${date}.csv`);
    console.log(`[DEBUG] Writing to CSV file: ${csvPath}`);

    try {
        const writer = csvWriter({ headers: [
            'timestamp', 'temperature_c', 'humidity_pct',
            'temp_avg_300s', 'humi_avg_300s',
            'temp_min_300s', 'temp_max_300s',
            'humi_min_300s', 'humi_max_300s'
        ], sendHeaders: !fs.existsSync(csvPath) });
        const csvFile = fs.createWriteStream(csvPath, { flags: 'a' });
        writer.pipe(csvFile);
        writer.write({
            timestamp,
            temperature_c,
            humidity_pct,
            temp_avg_300s,
            humi_avg_300s,
            temp_min_300s,
            temp_max_300s,
            humi_min_300s,
            humi_max_300s
        });
        writer.end();
        console.log(`[DEBUG] Successfully wrote data to ${csvPath}`);
        res.json({ message: 'Data saved successfully' });
    } catch (error) {
        console.error(`[ERROR] Error writing to CSV file ${csvPath}: ${error.message}`);
        res.status(500).json({ error: `Error writing CSV: ${error.message}` });
    }
});

// API to list available dates
app.get('/dates', (req, res) => {
    console.log('[DEBUG] Received request for /dates');
    fs.readdir(LOG_DIR, (err, files) => {
        if (err) {
            console.error(`[ERROR] Error reading logs directory: ${err.message}`);
            return res.status(500).json({ error: 'Error reading logs directory' });
        }
        const dates = files
            .filter(file => file.endsWith('.csv'))
            .map(file => file.replace('.csv', ''))
            .sort((a, b) => b.localeCompare(a));
        console.log(`[DEBUG] Found ${dates.length} dates: ${dates.join(', ')}`);
        res.json(dates);
    });
});

// Start server
app.listen(port, '0.0.0.0', () => {
    console.log(`[DEBUG] Server running at http://localhost:${port}`);
    console.log(`[DEBUG] Listening on all interfaces (0.0.0.0:${port})`);
});