import pytz
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def is_zero(f):
    f = float(f)
    return -0.1 < f < 0.1


class UserContributions(object):

    def __init__(self, user):
        self.user = user
        self.contributions = []

    def get_contribs(self, article=None, cls=None):
        contribs = self.contributions
        if article is not None:
            contribs = [contrib for contrib in contribs if contrib.article == article]
        if cls is not None:
            contribs = [contrib for contrib in self.contributions if isinstance(contrib, cls)]

        return contribs

    def add(self, contribution, include_zero=False):
        contribution.points = contribution.calculate_actual_points(self.contributions)
        if not is_zero(contribution.points) or include_zero:
            self.contributions.append(contribution)


class UserContribution(object):

    def __init__(self, rev, points, rule, description):
        self.rev = rev  # or use weakref???
        self.raw_points = points  # Points given to this contribution if considered in isolation
        self.points = points  # Points given to this contribution when taking limits etc. into account
        self.rule = rule
        self.description = description

    def is_negative(self):
        return self.raw_points < 0

    @property
    def article(self):
        return self.rev.article()

    @property
    def user(self):
        return self.rev.article().user()

    def calculate_actual_points(self, contributions):
        if self.rule.maxpoints is None:  # check that not 0.0
            return self.raw_points

        article = self.article
        article_contribs = contributions.get_contribs(article, type(self.rule))
        article_raw_points = sum([contrib.raw_points for contrib in article_contribs])
        article_points = sum([contrib.points for contrib in article_contribs])

        if is_zero(article_points - self.rule.maxpoints):
            # We are already at max. Only add the self if it's negative
            # and contributes to reducing the amount of points given to this article.
            if self.is_negative() and article_raw_points + self.raw_points < self.rule.maxpoints:
                return self.rule.maxpoints - article_raw_points - self.raw_points
            else:
                return 0.

        elif article_points + self.raw_points > self.rule.maxpoints:
            # We're reaching the max value and need to cap the number of points given
            # to this contribution.
            return self.rule.maxpoints - article_points   # TODO: Add to description in some way ' &gt; ' + _('max')

        return self.raw_points

            # rev.points.append([pts, ptype, txt + ' &gt; ' + _('max'), points])

        #elif not self.iszero(revpoints):
        # else:
        #     if self.iszero(points) and not include_zero:
        #         return False
        #     pts = points
        #     rev.points.append([points, ptype, txt, points])
        # if pts > 0.0:
        #     return True

    def get_points(self, ignore_max=False, ignore_suspension_period=False,
                   ignore_disqualification=False, ignore_point_deductions=False):

        # Check if article is disqualified
        if ignore_disqualification is False and self.article.key in self.user.disqualified_articles:
            logger.debug('Skipping revision from disqualified article %s', self.article.key)
            return 0.

        # Check if user is suspended
        if ignore_suspension_period is False and self.user.suspended_since is not None:
            dt = pytz.utc.localize(datetime.fromtimestamp(rev.timestamp))
            if dt >= self.user.suspended_since:
                logger.debug('Skipping revision %s in suspension period', self.rev.revid)
                return 0.

        p = 0.
        for revid, rev in self.revisions.items():
            dt = pytz.utc.localize(datetime.fromtimestamp(rev.timestamp))
            if ignore_suspension_period is True or self.user().suspended_since is None or dt < self.user().suspended_since:
                p += rev.get_points(ptype, ignore_max, ignore_point_deductions)
            else:
                logger.debug('!! Skipping revision %d in suspension period', revid)


    def get_points(self, ptype='', ignore_max=False, ignore_point_deductions=False):
        p = 0.0
        for pnt in self.points:
            if ptype == '' or pnt[1] == ptype:
                if ignore_max and len(pnt) > 3:
                    p += pnt[3]
                else:
                    p += pnt[0]

        if not ignore_point_deductions and (ptype == '' or ptype == 'trekk'):
            for points, reason in self.point_deductions:
                p -= points

        return p
