# ************************************************************
# Sequel Ace SQL dump
# Version 20033
#
# https://sequel-ace.com/
# https://github.com/Sequel-Ace/Sequel-Ace
#
# Host: tools.db.svc.eqiad.wmflabs (MySQL 5.5.5-10.1.39-MariaDB)
# Database: s51083__ukbot
# Generation Time: 2022-06-05 10:47:16 +0000
# ************************************************************


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
SET NAMES utf8mb4;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE='NO_AUTO_VALUE_ON_ZERO', SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;


# Dump of table articles
# ------------------------------------------------------------

DROP TABLE IF EXISTS `articles`;

CREATE TABLE `articles` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `site` varchar(50) COLLATE utf8mb4_bin NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `articles_site_name` (`site`,`name`(50)) USING BTREE
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;



# Dump of table contests
# ------------------------------------------------------------

DROP TABLE IF EXISTS `contests`;

CREATE TABLE `contests` (
  `contest_id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `site` varchar(50) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL,
  `name` varchar(100) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL,
  `ended` tinyint(1) unsigned NOT NULL DEFAULT '0',
  `closed` tinyint(1) unsigned NOT NULL DEFAULT '0',
  `start_date` timestamp NULL DEFAULT NULL,
  `end_date` timestamp NULL DEFAULT NULL,
  `update_date` timestamp NULL DEFAULT NULL,
  `last_job_id` varchar(50) DEFAULT NULL,
  `config` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`contest_id`),
  UNIQUE KEY `uq_site_name` (`site`,`name`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8;



# Dump of table contribs
# ------------------------------------------------------------

DROP TABLE IF EXISTS `contribs`;

CREATE TABLE `contribs` (
  `revid` int(11) unsigned NOT NULL,
  `site` varchar(50) COLLATE utf8mb4_bin NOT NULL DEFAULT '',
  `parentid` int(12) unsigned NOT NULL,
  `user` varchar(100) COLLATE utf8mb4_bin NOT NULL DEFAULT '',
  `page` varchar(255) COLLATE utf8mb4_bin NOT NULL DEFAULT '',
  `timestamp` datetime NOT NULL,
  `size` int(8) unsigned NOT NULL,
  `parentsize` int(8) unsigned NOT NULL,
  `parsedcomment` text COLLATE utf8mb4_bin,
  `ns` int(4) unsigned DEFAULT NULL,
  PRIMARY KEY (`revid`,`site`) USING BTREE,
  KEY `idx_parentid` (`parentid`),
  KEY `idx_user` (`user`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;



# Dump of table fulltexts
# ------------------------------------------------------------

DROP TABLE IF EXISTS `fulltexts`;

CREATE TABLE `fulltexts` (
  `revid` int(11) unsigned NOT NULL,
  `site` varchar(50) COLLATE utf8mb4_bin NOT NULL,
  `revtxt` mediumtext COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (`revid`,`site`) USING BTREE
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;



# Dump of table notifications
# ------------------------------------------------------------

DROP TABLE IF EXISTS `notifications`;

CREATE TABLE `notifications` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `contest` varchar(100) COLLATE utf8_bin NOT NULL,
  `site` varchar(50) COLLATE utf8_bin NOT NULL,
  `user` varchar(100) COLLATE utf8_bin NOT NULL,
  `class` varchar(50) COLLATE utf8_bin NOT NULL,
  `args` varchar(255) COLLATE utf8_bin NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;



# Dump of table prizes
# ------------------------------------------------------------

DROP TABLE IF EXISTS `prizes`;

CREATE TABLE `prizes` (
  `prize_id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `contest_id` int(11) unsigned NOT NULL,
  `site` varchar(50) COLLATE utf8_bin NOT NULL,
  `user` varchar(100) COLLATE utf8_bin NOT NULL,
  `timestamp` datetime NOT NULL,
  PRIMARY KEY (`prize_id`),
  KEY `contest_site_user` (`contest_id`,`site`,`user`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;



# Dump of table schemachanges
# ------------------------------------------------------------

DROP TABLE IF EXISTS `schemachanges`;

CREATE TABLE `schemachanges` (
  `version` int(4) unsigned NOT NULL,
  `commithash` varchar(180) COLLATE utf8_bin NOT NULL,
  `dateapplied` datetime NOT NULL,
  PRIMARY KEY (`version`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;



# Dump of table stats
# ------------------------------------------------------------

DROP TABLE IF EXISTS `stats`;

CREATE TABLE `stats` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `contestsite` varchar(50) NOT NULL,
  `contest` varchar(100) NOT NULL DEFAULT '',
  `contribsite` varchar(50) NOT NULL DEFAULT '',
  `dimension` varchar(20) NOT NULL DEFAULT '',
  `value` int(5) unsigned NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;



# Dump of table users
# ------------------------------------------------------------

DROP TABLE IF EXISTS `users`;

CREATE TABLE `users` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `site` varchar(50) COLLATE utf8_bin NOT NULL,
  `contest` varchar(100) COLLATE utf8_bin NOT NULL,
  `user` varchar(100) COLLATE utf8_bin NOT NULL,
  `points` float(10,4) unsigned NOT NULL,
  `bytes` int(8) unsigned NOT NULL,
  `pages` int(5) unsigned NOT NULL DEFAULT '0',
  `newpages` int(5) unsigned NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_bin;




/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;
/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
