import { BG, buildURL, GOOG_API_KEY } from 'bgutils-js';
import { JSDOM } from 'jsdom';
import { Innertube } from 'youtubei.js';

const challengeCache = new Map();
const CACHE_TTL = 30 * 60 * 1000; // 30 minutes

function createBrowserEnv() {
  const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', {
    url: 'https://www.youtube.com',
    pretendToBeVisual: true,
  });

  Object.defineProperty(globalThis, 'window', { value: dom.window, configurable: true, writable: true });
  Object.defineProperty(globalThis, 'document', { value: dom.window.document, configurable: true, writable: true });
  Object.defineProperty(globalThis, 'location', { value: dom.window.location, configurable: true, writable: true });
  Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true, writable: true });

  return dom;
}


export async function solveBotGuard(cookieString) {
  console.log('[BotGuard] Starting challenge solve...');

  // QUAN TRONG: challenge phai duoc tao cho client STUDIO (clientName 62 = WEB_CREATOR),
  // nguoc lai challenge co d=1 (WEB) va metadata_update cua Studio se bo qua (no-op).
  // Dung client_type ngay tu create de context.client duoc set day du (khong chi ten).
  const innertube = await Innertube.create({
    retrieve_player: false,
    cookie: cookieString,
    client_type: 'WEB_CREATOR',
  });

  console.log('[BotGuard] Fetching challenge from /att/get (client WEB_CREATOR / d=62)...');
  const challengeResponse = await innertube.getAttestationChallenge('ENGAGEMENT_TYPE_UNBOUND');

  if (!challengeResponse.bg_challenge) {
    throw new Error('Could not get challenge from YouTube Studio /att/get');
  }

  const bgChallenge = challengeResponse.bg_challenge;
  console.log('[BotGuard] Challenge retrieved from /att/get. Global name:', bgChallenge.global_name);

  const dom = createBrowserEnv();

  try {
    let vmScript = bgChallenge.interpreter_url.private_do_not_access_or_else_safe_script_wrapped_value;
    if (!vmScript) {
      const scriptUrl = bgChallenge.interpreter_url.private_do_not_access_or_else_trusted_resource_url_wrapped_value;
      if (!scriptUrl) {
        throw new Error('No VM script or URL found in challenge');
      }
      console.log(`[BotGuard] Fetching VM script from URL: https:${scriptUrl}`);
      const res = await fetch(`https:${scriptUrl}`);
      vmScript = await res.text();
    }

    new Function(vmScript)();

    const botguard = await BG.BotGuardClient.create({
      program: bgChallenge.program,
      globalName: bgChallenge.global_name,
      globalObj: globalThis
    });

    const webPoSignalOutput = [];
    const botguardResponse = await botguard.snapshot({ webPoSignalOutput });

    if (!botguardResponse) {
      throw new Error('Failed to generate botguardResponse snapshot');
    }

    console.log('[BotGuard] Successfully solved challenge');

    return {
      botguardResponse,
      challenge: challengeResponse.challenge,
      visitorData: innertube.session.context.client.visitorData || '',
    };
  } finally {
    // Cleanup JSDOM
    dom.window.close();
  }
}


export async function getCtxToken(cookieString, infoAccount, authorization, botguardResponse) {
  console.log('[BotGuard] Getting ctx token from /att/esr...');

  const payload = {
    context: {
      client: {
        clientName: 62,
        clientVersion: '1.20260709.05.00',
        hl: 'vi',
        gl: 'VN',
        experimentsToken: '',
        utcOffsetMinutes: 420,
        userInterfaceTheme: 'USER_INTERFACE_THEME_LIGHT',
        screenWidthPoints: 1111,
        screenHeightPoints: 927,
        screenPixelDensity: 1,
        screenDensityFloat: 1,
      },
      request: {
        returnLogEntry: true,
        internalExperimentFlags: [],
        eats: infoAccount.eats,
        consistencyTokenJars: [],
      },
      user: {
        onBehalfOfUser: infoAccount.delegated_session_id,
        delegationContext: {
          externalChannelId: infoAccount.channel_id,
          roleType: {
            channelRoleType: 'CREATOR_CHANNEL_ROLE_TYPE_OWNER',
          },
        },
        serializedDelegationContext: infoAccount.serialized_delegation_context,
      },
      clickTracking: {
        visualElement: {
          veType: 31402,
        },
      },
    },
    challenge: '1',
    botguardResponse: botguardResponse,
    xguardClientStatus: 0,
  };

  const response = await fetch('https://studio.youtube.com/youtubei/v1/att/esr?alt=json', {
    method: 'POST',
    headers: {
      'accept': '*/*',
      'authorization': `SAPISIDHASH ${authorization}`,
      'content-type': 'application/json',
      'origin': 'https://studio.youtube.com',
      'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36',
      'cookie': cookieString,
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  
  if (!data.ctx) {
    console.error('[BotGuard] /att/esr response:', JSON.stringify(data, null, 2));
    throw new Error('Failed to get ctx token from /att/esr');
  }

  console.log('[BotGuard] Got ctx token');
  return data.ctx;
}


export async function solveBotGuardCached(cookieString) {
  const cacheKey = cookieString.substring(0, 50);
  const cached = challengeCache.get(cacheKey);

  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    console.log('[BotGuard] Using cached token');
    return cached.result;
  }

  const result = await solveBotGuard(cookieString);
  challengeCache.set(cacheKey, {
    result,
    timestamp: Date.now(),
  });

  return result;
}


export function cleanupCache() {
  const now = Date.now();
  for (const [key, value] of challengeCache) {
    if (now - value.timestamp >= CACHE_TTL) {
      challengeCache.delete(key);
    }
  }
}

setInterval(cleanupCache, 10 * 60 * 1000);
