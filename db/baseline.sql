CREATE TABLE contests (
  name TEXT,
  ended INTEGER NOT NULL,
  closed INTEGER NOT NULL,
  PRIMARY KEY(name)  
);
CREATE TABLE contribs (
  revid INTEGER NOT NULL,
  site TEXT NOT NULL,
  parentid INTEGER NOT NULL,
  user TEXT NOT NULL, 
  page TEXT NOT NULL, 
  timestamp DATETIME NOT NULL, 
  size  INTEGER NOT NULL,
  parentsize  INTEGER NOT NULL,
  PRIMARY KEY(revid, site)
);
CREATE TABLE fulltexts (
  revid INTEGER NOT NULL,
  site TEXT NOT NULL,
  revtxt TEXT NOT NULL,
  PRIMARY KEY(revid, site)  
);
CREATE TABLE notifications (
  id INTEGER NOT NULL PRIMARY KEY,
  contest TEXT,
  user TEXT NOT NULL,
  class TEXT NOT NULL,
  args TEXT NOT NULL
);
CREATE TABLE users (
  contest TEXT,
  user TEXT NOT NULL,
  week INTEGER NOT NULL,
  points REAL NOT NULL,
  bytes INTEGER NOT NULL,
  newpages INTEGER NOT NULL,
  week2 INTEGER NOT NULL, 
  PRIMARY KEY (contest,user)
);
CREATE TABLE schemachanges (
  version INT PRIMARY KEY,
  commithash TEXT NOT NULL,
  dateapplied DATETIME NOT NULL
);
