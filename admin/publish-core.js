/* Manual publishing only; no crawling or GitHub Actions dispatch. */
(function (global) {
  'use strict';
  var FILES = ['games.json', 'intel.json', 'deals.json'];
  var own = function (obj, key) { return Object.prototype.hasOwnProperty.call(obj, key); };
  var clone = function (value) { return JSON.parse(JSON.stringify(value)); };

  function stable(value) {
    if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']';
    if (value && typeof value === 'object') {
      return '{' + Object.keys(value).sort().map(function (key) { return JSON.stringify(key) + ':' + stable(value[key]); }).join(',') + '}';
    }
    return JSON.stringify(value);
  }

  function identity(item) {
    if (typeof item === 'string' || typeof item === 'number') item = { link: String(item) };
    item = item || {};
    if (item.steam_id) return 'app/' + item.steam_id;
    if (item.epic_slug) return 'p/' + String(item.epic_slug).replace(/\/home\/?$/, '').toLowerCase();
    var link = String(item.link || item.custom_url || item.url || item.id || '').trim().toLowerCase();
    var steam = link.match(/^(?:https:\/\/store\.steampowered\.com\/)?app\/(\d+)(?:[/?#].*)?$/);
    if (steam) return 'app/' + steam[1];
    if (/^\d+$/.test(link)) return 'app/' + link;
    var epic = link.match(/^(?:https:\/\/store\.epicgames\.com\/(?:[a-z]{2}(?:-[a-z]{2})?\/)?)?p\/([a-z0-9-]+)(?:\/home)?(?:[/?#].*)?$/);
    if (epic) return 'p/' + epic[1];
    if (String(item.platform || '').toLowerCase() === 'epic' && /^[a-z0-9-]+$/.test(link)) return 'p/' + link;
    return link || String(item.zh_title || item.name || item.title || '').trim().toLowerCase();
  }

  function blocked(item, rules) {
    var key = identity(item);
    var title = String(item.zh_title || item.name || item.title || '').toLowerCase();
    return (rules || []).some(function (rule) {
      var raw = String(rule || '').trim().toLowerCase();
      if (!raw) return false;
      var normalized = identity(rule);
      if (/^(?:app\/\d+|p\/[a-z0-9-]+)$/.test(normalized)) return normalized === key;
      return key.indexOf(raw) >= 0 || title.indexOf(raw) >= 0;
    });
  }

  function validateLive(live) {
    if (!live || !Array.isArray(live['games.json']) || !Array.isArray(live['deals.json'])) {
      throw new Error('线上游戏或特惠数据读取不完整，未发布');
    }
    var intel = live['intel.json'];
    if (!intel || typeof intel !== 'object' || Array.isArray(intel)) throw new Error('线上情报数据读取不完整，未发布');
    ['to_paid', 'freeplay', 'free_weekend'].forEach(function (key) {
      if (own(intel, key) && !Array.isArray(intel[key])) throw new Error('线上情报分类格式错误：' + key);
    });
  }

  function recordFromRule(rule, original) {
    var record = clone(original || {});
    var key = identity(rule);
    if (!key) throw new Error('新增游戏需要填写领取链接或 App ID');
    if (key.indexOf('app/') === 0) {
      record.steam_id = key.slice(4); record.platform = 'Steam';
    } else if (key.indexOf('p/') === 0) {
      record.epic_slug = key.slice(2); record.platform = 'Epic Games';
    } else {
      if (!/^https?:\/\//i.test(key)) throw new Error('无法识别游戏链接：' + key);
      record.custom_url = rule.link || rule.custom_url || rule.url;
      record.platform = rule.platform === 'steam' ? 'Steam' : (rule.platform === 'epic' ? 'Epic Games' : (rule.platform || record.platform));
    }
    var aliases = { name: 'zh_title', desc: 'short_description', description: 'short_description', dec: 'short_description' };
    ['name', 'desc', 'description', 'dec', 'thumbnail', 'original_price', 'title_url', 'button_url', 'sort_order', 'start_date'].forEach(function (field) {
      if (own(rule, field) && rule[field] !== '' && rule[field] != null) record[aliases[field] || field] = rule[field];
    });
    if (own(rule, 'sort_order') && rule.sort_order === '') delete record.sort_order;
    if (own(rule, 'end_date')) record.end_date = rule.end_date || '限免进行中';
    if (record.end_date && !['N/A', '限免进行中', '近期即将转付费'].includes(record.end_date) && !Number.isFinite(Date.parse(record.end_date))) {
      throw new Error('活动截止时间无效：' + (record.zh_title || key));
    }
    record.type = rule.type || record.type || '100_off';
    if (record.type === 'weekend') record.type = 'freeplay';
    if (!['100_off', 'upcoming', 'to_paid', 'freeplay'].includes(record.type)) {
      throw new Error('该类型暂不支持手动发布：' + record.type);
    }
    record.is_upcoming = record.type === 'upcoming';
    if (!record.zh_title) throw new Error('新增游戏需要填写展示标题：' + key);
    return record;
  }

  function sorted(items) {
    function order(item) {
      if (item.sort_order === '' || item.sort_order == null) return 999999;
      var value = Number(item.sort_order);
      return Number.isFinite(value) ? value : 999999;
    }
    return items.sort(function (a, b) {
      var upcoming = Number(Boolean(a.is_upcoming || a.type === 'upcoming')) - Number(Boolean(b.is_upcoming || b.type === 'upcoming'));
      return upcoming || order(a) - order(b) || String(a.zh_title || a.name || '').localeCompare(String(b.zh_title || b.name || ''), 'zh-CN');
    });
  }

  function automaticOrder(items) {
    function date(value) {
      var parsed = Date.parse(value || '');
      return Number.isFinite(parsed) ? parsed : Infinity;
    }
    return items.map(function (item, index) { return { item: item, index: index }; }).sort(function (a, b) {
      var au = Boolean(a.item.is_upcoming || a.item.type === 'upcoming');
      var bu = Boolean(b.item.is_upcoming || b.item.type === 'upcoming');
      if (au !== bu) return au ? 1 : -1;
      var ad = date((au && a.item.start_date) || a.item.end_date || a.item.endDate);
      var bd = date((bu && b.item.start_date) || b.item.end_date || b.item.endDate);
      return ad === bd ? a.index - b.index : (ad < bd ? -1 : 1);
    }).map(function (entry) { return entry.item; });
  }

  function applyManager(live, manager, previousManager, now) {
    validateLive(live);
    now = now == null ? Date.now() : now;
    var result = clone(live);
    var buckets = [result['games.json']];
    var intel = result['intel.json'];
    ['to_paid', 'freeplay', 'free_weekend'].forEach(function (key) {
      if (Array.isArray(intel[key])) buckets.push(intel[key]);
    });
    var rules = manager.add || [];
    var keep = new Set(rules.map(identity));
    var removed = new Set(((previousManager || {}).add || []).map(identity).filter(function (key) { return !keep.has(key); }));
    var originals = new Map();
    buckets.forEach(function (bucket) { bucket.forEach(function (item) { originals.set(identity(item), item); }); });
    buckets.forEach(function (bucket) {
      for (var i = bucket.length - 1; i >= 0; i--) {
        if (removed.has(identity(bucket[i])) || blocked(bucket[i], manager.disable)) bucket.splice(i, 1);
      }
    });
    rules.forEach(function (rule) {
      if (blocked(rule, manager.disable)) return;
      var key = identity(rule);
      var record = recordFromRule(rule, originals.get(key));
      buckets.forEach(function (bucket) {
        for (var i = bucket.length - 1; i >= 0; i--) if (identity(bucket[i]) === key) bucket.splice(i, 1);
      });
      var target = result['games.json'];
      if (record.type === 'to_paid' || record.type === 'freeplay') {
        if (!Array.isArray(intel[record.type])) { intel[record.type] = []; buckets.push(intel[record.type]); }
        target = intel[record.type];
      }
      target.push(record);
    });
    var orders = new Map((manager.sort || []).map(function (rule) { return [identity(rule), rule.sort_order]; }));
    var removedOrders = new Set(((previousManager || {}).sort || []).map(identity).filter(function (key) { return !orders.has(key) && !keep.has(key); }));
    buckets.forEach(function (bucket) {
      for (var i = bucket.length - 1; i >= 0; i--) {
        var item = bucket[i];
        var end = Date.parse(item.end_date || item.endDate || '');
        if (Number.isFinite(end) && end <= now) { bucket.splice(i, 1); continue; }
        if (removedOrders.has(identity(item))) delete item.sort_order;
        if (orders.has(identity(item))) item.sort_order = orders.get(identity(item));
      }
      sorted(bucket);
    });
    result['deals.json'] = result['deals.json'].filter(function (item) { return !blocked(item, manager.disable); });
    // Preserve deal-specific fields, screenshots and all unknown intel buckets.
    return result;
  }

  async function publish(options) {
    var githubSaved = false;
    var published = [];
    try {
      var preflight = await Promise.all([options.readManager(), options.readLive()]);
      if ((preflight[0].sha || '') !== (options.expectedSha || '')) {
        throw new Error('GitHub 配置已被其他操作修改，请刷新后重新调整');
      }
      var live = preflight[1];
      var output = applyManager(live, options.manager, options.previousManager);
      var changed = FILES.filter(function (file) { return stable(live[file]) !== stable(output[file]); });
      options.checkpoint();
      await options.syncManager(preflight[0]);
      githubSaved = true;
      for (var i = 0; i < changed.length; i++) {
        var file = changed[i];
        // Detect a collector/editor update between loading and publishing a file.
        var current = await options.readFile(file);
        if (stable(current) !== stable(live[file])) throw new Error('线上 ' + file + ' 刚刚发生变化，请点击重试以合并最新内容');
        await options.writeFile(file, output[file]);
        published.push(file);
      }
      return { files: published, live: output };
    } catch (error) {
      error.githubSaved = githubSaved;
      error.publishedFiles = published;
      throw error;
    }
  }

  global.EtAdminPublish = { identity: identity, blocked: blocked, stable: stable, automaticOrder: automaticOrder, applyManager: applyManager, publish: publish };
})(typeof window === 'undefined' ? globalThis : window);
