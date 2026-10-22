/** Cover Studio 每个画幅的自动布局配置。用户手动编辑的比例保留独立覆盖。 */

export const PROFILES = Object.freeze({
  "3:4": {
    titleTop: .247, titleMaxWidth: .89, titleHeight: .31,
    subtitleMinTop: .44, subtitleMaxBottom: .81,
    accountMinTop: .695, avatarMinTop: .65,
    safeMargin: .055, flowGap: .031,
  },
  "9:16": {
    titleTop: .207, titleMaxWidth: .89, titleHeight: .30,
    subtitleMinTop: .415, subtitleMaxBottom: .80,
    accountMinTop: .71, avatarMinTop: .665,
    safeMargin: .055, flowGap: .028,
  },
  "16:9": {
    titleTop: .13, titleMaxWidth: .89, titleHeight: .35,
    subtitleMinTop: .465, subtitleMaxBottom: .78,
    accountMinTop: .755, avatarMinTop: .73,
    safeMargin: .045, flowGap: .033,
  },
  "4:3": {
    titleTop: .177, titleMaxWidth: .89, titleHeight: .34,
    subtitleMinTop: .475, subtitleMaxBottom: .79,
    accountMinTop: .755, avatarMinTop: .71,
    safeMargin: .05, flowGap: .03,
  },
  "4:5": {
    titleTop: .227, titleMaxWidth: .89, titleHeight: .31,
    subtitleMinTop: .455, subtitleMaxBottom: .81,
    accountMinTop: .72, avatarMinTop: .675,
    safeMargin: .055, flowGap: .03,
  },
  "1:1": {
    titleTop: .205, titleMaxWidth: .89, titleHeight: .35,
    subtitleMinTop: .52, subtitleMaxBottom: .82,
    accountMinTop: .77, avatarMinTop: .745,
    safeMargin: .055, flowGap: .03,
  },
});

export function getProfile(ratio) {
  const profile = PROFILES[ratio];
  if (!profile) throw Error("未知画幅的排版配置：" + ratio);
  return profile;
}
