// Mail relay for the Momentum Screener cloud scan (see mail_relay.py).
// Setup: script.google.com -> New project -> paste this file ->
// Services (+) -> Gmail API -> Add -> Deploy -> New deployment -> Web app,
// Execute as: Me, Who has access: Anyone -> copy the /exec URL.

const TOKEN = 'PASTE_THE_SAME_VALUE_AS_THE_MAIL_RELAY_TOKEN_SECRET';

function doPost(e) {
  const data = JSON.parse(e.postData.contents);
  if (data.token !== TOKEN) {
    return ContentService.createTextOutput('forbidden');
  }
  try {
    Gmail.Users.Messages.send({ raw: data.raw }, 'me');
    return ContentService.createTextOutput('ok');
  } catch (err) {
    return ContentService.createTextOutput('error: ' + err);
  }
}
