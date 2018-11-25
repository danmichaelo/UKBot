
CREATE TABLE `contests` (
  `contest_id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `site` varchar(50) NOT NULL,
  `name` varchar(100) NOT NULL,
  `ended` tinyint(1) unsigned NOT NULL DEFAULT '0',
  `closed` tinyint(1) unsigned NOT NULL DEFAULT '0',
  `start_date` timestamp NULL DEFAULT NULL,
  `end_date` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`contest_id`),
  UNIQUE KEY `uq_site_name` (`site`,`name`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE `contribs` (
  `revid` int(11) unsigned NOT NULL,
  `site` varchar(50) NOT NULL DEFAULT '',
  `parentid` int(12) unsigned NOT NULL,
  `user` varchar(100) NOT NULL DEFAULT '',
  `page` varchar(255) NOT NULL DEFAULT '',
  `timestamp` datetime NOT NULL,
  `size` int(8) unsigned NOT NULL,
  `parentsize` int(8) unsigned NOT NULL,
  `parsedcomment` text,
  `ns` int(4) unsigned NOT NULL,
  PRIMARY KEY (`revid`,`site`),
  KEY `idx_parentid` (`parentid`),
  KEY `idx_user` (`user`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE `articles` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `site` varchar(50) COLLATE utf8mb4_bin NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `articles_site_name` (`site`,`name`(50))
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE `fulltexts` (
  `revid` int(11) unsigned NOT NULL,
  `site` varchar(50) COLLATE utf8mb4_bin NOT NULL,
  `revtxt` mediumblob NOT NULL,
  PRIMARY KEY (`revid`,`site`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE `notifications` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `contest` varchar(100) NOT NULL,
  `site` varchar(50) NOT NULL,
  `user` varchar(100) NOT NULL,
  `class` varchar(50) NOT NULL,
  `args` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;

CREATE TABLE `prizes` (
  `prize_id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `contest_id` int(11) unsigned NOT NULL,
  `site` varchar(50) NOT NULL,
  `user` varchar(100) NOT NULL,
  `timestamp` datetime NOT NULL,
  PRIMARY KEY (`prize_id`),
  KEY `contest_site_user` (`contest_id`,`site`,`user`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;

CREATE TABLE `schemachanges` (
  `version` int(4) unsigned NOT NULL,
  `commithash` varchar(180) NOT NULL,
  `dateapplied` datetime NOT NULL,
  PRIMARY KEY (`version`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;

CREATE TABLE `users` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `site` varchar(50) NOT NULL,
  `contest` varchar(100) NOT NULL,
  `user` varchar(100) NOT NULL,
  `week` int(2) unsigned NOT NULL,
  `points` float(10,4) NOT NULL,
  `bytes` int(8) NOT NULL,
  `newpages` int(5) unsigned NOT NULL,
  `week2` int(2) unsigned NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;
