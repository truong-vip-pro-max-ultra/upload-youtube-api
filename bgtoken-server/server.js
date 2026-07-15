import express from 'express';
import { solveBotGuardCached, getCtxToken, cleanupCache } from './botguard.js';
import { Innertube } from 'youtubei.js';
import crypto from 'crypto';

const app = express();
const PORT = process.env.PORT || 4416;

const stats = {
  totalRequests: 0,
  successfulSolves: 0,
  failedSolves: 0,
  totalCtxRequests: 0,
  startTime: Date.now(),
};

app.use(express.json({ limit: '1mb' }));

app.use((req, res, next) => {
  const start = Date.now();
  res.on('finish', () => {
    const duration = Date.now() - start;
    console.log(`[${new Date().toISOString()}] ${req.method} ${req.path} - ${res.statusCode} (${duration}ms)`);
  });
  next();
});

app.post('/solve', async (req, res) => {
  stats.totalRequests++;
  
  const { cookie } = req.body;
  
  if (!cookie) {
    return res.status(400).json({ 
      success: false, 
      error: 'Missing "cookie" field in request body' 
    });
  }

  try {
    console.log(`[Server] Solving BotGuard for cookie hash: ${crypto.createHash('md5').update(cookie.substring(0, 100)).digest('hex').substring(0, 8)}...`);
    
    const result = await solveBotGuardCached(cookie);
    
    stats.successfulSolves++;
    
    res.json({
      success: true,
      botguardResponse: result.botguardResponse,
      visitorData: result.visitorData,
    });
  } catch (error) {
    stats.failedSolves++;
    console.error('[Server] Solve error:', error.message);
    
    res.status(500).json({
      success: false,
      error: error.message,
      stack: process.env.NODE_ENV === 'development' ? error.stack : undefined,
    });
  }
});


app.post('/get-ctx', async (req, res) => {
  stats.totalCtxRequests++;
  
  const { cookie, infoAccount, authorization, botguardResponse } = req.body;
  
  if (!cookie || !infoAccount || !authorization || !botguardResponse) {
    return res.status(400).json({
      success: false,
      error: 'Missing required fields: cookie, infoAccount, authorization, botguardResponse',
    });
  }

  try {
    const ctx = await getCtxToken(cookie, infoAccount, authorization, botguardResponse);
    
    res.json({
      success: true,
      ctx,
    });
  } catch (error) {
    console.error('[Server] Get-ctx error:', error.message);
    
    res.status(500).json({
      success: false,
      error: error.message,
    });
  }
});


app.post('/full-solve', async (req, res) => {
  stats.totalRequests++;
  
  const { cookie, infoAccount, authorization } = req.body;
  
  if (!cookie || !infoAccount || !authorization) {
    return res.status(400).json({
      success: false,
      error: 'Missing required fields: cookie, infoAccount, authorization',
    });
  }

  try {
    const bgResult = await solveBotGuardCached(cookie);
    stats.successfulSolves++;

    const ctx = await getCtxToken(cookie, infoAccount, authorization, bgResult.botguardResponse);

    res.json({
      success: true,
      ctx,
      botguardResponse: bgResult.botguardResponse,
      visitorData: bgResult.visitorData,
    });
  } catch (error) {
    stats.failedSolves++;
    console.error('[Server] Full-solve error:', error.message);
    
    res.status(500).json({
      success: false,
      error: error.message,
    });
  }
});


async function getAccountInfo(cookieString) {
  try {
    const res = await fetch("https://studio.youtube.com", {
      headers: {
        'Cookie': cookieString,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
      }
    });
    const text = await res.text();
    
    const reSearch = (str, key) => {
      const match = new RegExp(`"${key}":\\s*"([^"]+)"`).exec(str);
      return match ? match[1] : null;
    };

    return {
      channelId: reSearch(text, 'CHANNEL_ID'),
      delegationContext: reSearch(text, 'INNERTUBE_CONTEXT_SERIALIZED_DELEGATION_CONTEXT'),
      delegatedSessionId: reSearch(text, 'DELEGATED_SESSION_ID')
    };
  } catch (error) {
    console.error('[Server] Failed to fetch account info from YouTube Studio:', error.message);
    return null;
  }
}


app.post('/upload', express.raw({ type: 'video/*', limit: '10gb' }), async (req, res) => {
  stats.totalRequests++;
  
  const cookieString = req.headers['x-cookie-string'];
  const title = decodeURIComponent(req.headers['x-video-title'] || '');
  const description = decodeURIComponent(req.headers['x-video-description'] || '');
  const privacy = req.headers['x-video-privacy'] || 'PRIVATE';

  if (!cookieString) {
    return res.status(400).json({ success: false, error: 'Missing x-cookie-string header' });
  }

  try {
    console.log(`[Server] Fetching account profile details...`);
    const infoAccount = await getAccountInfo(cookieString);

    console.log(`[Server] Initializing Innertube session for upload...`);
    const innertube = await Innertube.create({
      retrieve_player: false,
      cookie: cookieString,
      on_behalf_of_user: infoAccount?.delegatedSessionId || undefined
    });

    if (!innertube.session.logged_in) {
      return res.status(401).json({ success: false, error: 'Not logged in. Invalid cookies.' });
    }

    if (infoAccount) {
      console.log(`[Server] Session channel ID: ${infoAccount.channelId}`);
      if (infoAccount.delegatedSessionId) {
        console.log(`[Server] Applying delegated session ID (Brand Account): ${infoAccount.delegatedSessionId}`);
        innertube.session.context.user.onBehalfOfUser = infoAccount.delegatedSessionId;
      }
      if (infoAccount.delegationContext) {
        innertube.session.context.user.serializedDelegationContext = infoAccount.delegationContext;
      }
      if (infoAccount.channelId) {
        innertube.session.context.user.delegationContext = {
          externalChannelId: infoAccount.channelId,
          roleType: {
            channelRoleType: 'CREATOR_CHANNEL_ROLE_TYPE_OWNER'
          }
        };
      }
    }

    const videoBuffer = req.body;
    if (!videoBuffer || videoBuffer.length === 0) {
      return res.status(400).json({ success: false, error: 'Empty video payload received' });
    }

    console.log(`[Server] Uploading video: "${title}", size: ${videoBuffer.length} bytes...`);
    const response = await innertube.studio.upload(videoBuffer.buffer, {
      title,
      description,
      privacy
    });

    const videoId = response.videoId || response.data?.videoId;
    console.log(`[Server] Upload successful: Video ID: ${videoId}`);
    res.json({
      success: true,
      videoId: videoId,
      data: response
    });
  } catch (error) {
    console.error('[Server] Upload error:', error.message);
    res.status(500).json({ success: false, error: error.message });
  }
});


app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    uptime: Math.floor((Date.now() - stats.startTime) / 1000),
  });
});


app.get('/stats', (req, res) => {
  res.json({
    ...stats,
    uptimeSeconds: Math.floor((Date.now() - stats.startTime) / 1000),
  });
});

app.listen(PORT, () => {
  console.log('╔════════════════════════════════════════════╗');
  console.log('║  BotGuard Token Server                    ║');
  console.log(`║  Running on http://localhost:${PORT}          ║`);
  console.log('║                                            ║');
  console.log('║  Endpoints:                                ║');
  console.log('║    POST /solve      - Solve BG challenge   ║');
  console.log('║    POST /get-ctx    - Get ctx token        ║');
  console.log('║    POST /full-solve - Solve + get ctx      ║');
  console.log('║    GET  /health     - Health check         ║');
  console.log('║    GET  /stats      - Server stats         ║');
  console.log('╚════════════════════════════════════════════╝');
});
