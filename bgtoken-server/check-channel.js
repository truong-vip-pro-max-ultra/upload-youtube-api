import { Innertube } from 'youtubei.js';
import fs from 'fs';

async function test() {
  const cookieJson = JSON.parse(fs.readFileSync('../cookies/cookies.json', 'utf8'));
  const cookieString = cookieJson.map(c => `${c.name}=${c.value}`).join('; ');

  console.log('Initializing Innertube...');
  const innertube = await Innertube.create({
    retrieve_player: false,
    cookie: cookieString,
    on_behalf_of_user: '116702359715477581962'
  });

  if (!innertube.session.logged_in) {
    console.log('Not logged in!');
    return;
  }

  console.log('Logged in successfully!');
  
  // Call /web/get_settings or similar to see account channel list
  try {
    const response = await innertube.actions.execute('/web/get_settings', {});
    console.log('Channel ID from settings:', response.data.settingMenuItems?.[0]?.settingMenuItemRenderer?.title?.simpleText || 'Not found');
  } catch (e) {
    // try to get channel list
    try {
      const channelInfo = await innertube.actions.execute('/channel/get_profile_header', {});
      console.log('Channel Profile Header Title:', channelInfo.data.header?.c4TabbedHeaderRenderer?.title);
    } catch (err) {
      console.log('Could not get profile header:', err.message);
    }
  }

  // Check the account info parsed by our regex matching
  try {
    // Get info using our regex code logic
    const res = await fetch("https://studio.youtube.com", {
      headers: {
        'Cookie': cookieString,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
      }
    });
    const text = await res.text();
    const eats = reSearch(text, 'EATS');
    const channelId = reSearch(text, 'CHANNEL_ID');
    const delegationContext = reSearchOptional(text, 'INNERTUBE_CONTEXT_SERIALIZED_DELEGATION_CONTEXT');
    const delegatedSessionId = reSearchOptional(text, 'DELEGATED_SESSION_ID');

    console.log('Parsed eats:', eats ? 'Found' : 'Not found');
    console.log('Parsed channelId:', channelId);
    console.log('Parsed delegationContext:', delegationContext);
    console.log('Parsed delegatedSessionId:', delegatedSessionId);
  } catch (err) {
    console.log('Error parsing studio page:', err.message);
  }
}

function reSearch(text, key) {
  const match = new RegExp(`"${key}":\\s*"([^"]+)"`).exec(text);
  return match ? match[1] : null;
}

function reSearchOptional(text, key) {
  const match = new RegExp(`"${key}":\\s*"([^"]+)"`).exec(text);
  return match ? match[1] : null;
}

test().catch(console.error);
