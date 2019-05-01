import pytz
import logging
import weakref
from datetime import datetime

logger = logging.getLogger(__name__)


def is_zero(f):
    f = float(f)
    return -0.1 < f < 0.1


class UserContributions(object):

    def __init__(self, user):
        self.user = weakref.ref(user)
        self.contributions = []

    def add(self, contribution):
        """
        Add a contribution and calculate the actual number of points given to it when
        taking point capping into account.
        
        After capping, some contributions may end up with zero points, but we still store
        them so we can collect statistics like  'total number of words'.

        Params:
            contribution: The UserContribution to add
        """

        logger.debug(
            '[[%s]] @ %s: Add %.1f points from %s: "%s"', contribution.rev.article().name, contribution.rev.revid,
            contribution.points, type(contribution.rule).__name__, contribution.description
        )
        contribution.points = self.calculate_contribution_points(contribution)
        self.contributions.append(contribution)
        # Reminder to self: We do not filter out contributions that end up giving zero points after a limit.
        # This is so we can make statistics on metrics like total number of words.

    def get(self, cls=None, article=None, revision=None):
        """
        Return contributions, optionally filtered by article and/or rule type.

        Params:
            cls: Filter by rule class
            article: Filter by article
            revision: Filter by revision
        """
        contribs = self.contributions
        if cls is not None:
            contribs = [contrib for contrib in self.contributions if isinstance(contrib, cls)]
        if article is not None:
            contribs = [contrib for contrib in contribs if contrib.article == article]
        if revision is not None:
            contribs = [contrib for contrib in contribs if contrib.rev == revision]

        return contribs

    def calculate_contribution_points(self, contribution):
        """
        Get the actual points for a given contribution, taking capping into account.
        """
        if contribution.rule.maxpoints is None:  # check that not 0.0
            return contribution.raw_points

        article = contribution.article
        article_contribs = self.get(article=article, cls=type(contribution.rule))
        article_raw_points = sum([contrib.raw_points for contrib in article_contribs])
        article_points = sum([contrib.points for contrib in article_contribs])

        if is_zero(article_points - contribution.rule.maxpoints):
            logger.debug('Ignoring contribution, already reached the point limit (%.1f) for %s.',
                         contribution.rule.maxpoints, type(contribution.rule).__name__)
            # We are already at max. Only add the self if it's negative
            # and contributes to reducing the amount of points given to this article.
            if contribution.is_negative() and article_raw_points + contribution.raw_points < contribution.rule.maxpoints:
                return contribution.rule.maxpoints - article_raw_points - contribution.raw_points
            else:
                return 0.

        elif article_points + contribution.raw_points > contribution.rule.maxpoints:
            # We're reaching the max value and need to cap the number of points given
            # to this contribution.
            logger.debug('Reaching the point limit (%.1f) for %s.',
                         contribution.rule.maxpoints, type(contribution.rule).__name__)
            return contribution.rule.maxpoints - article_points   # TODO: Add to description in some way ' &gt; ' + _('max')

        return contribution.raw_points

        # rev.points.append([pts, ptype, txt + ' &gt; ' + _('max'), points])

        #elif not self.iszero(revpoints):
        # else:
        #     if self.iszero(points) and not include_zero:
        #         return False
        #     pts = points
        #     rev.points.append([points, ptype, txt, points])
        # if pts > 0.0:
        #     return True

    def get_article_points(self, article, ignore_max=False, ignore_suspension_period=False,
                           ignore_disqualification=False, ignore_point_deductions=False):

        # Check if article is disqualified
        if ignore_disqualification is False and article.key in self.user().disqualified_articles:
            logger.debug('Skipping revision from disqualified article %s', article.key)
            return 0.

        points = 0.
        for revision in article.revisions.values():

            # Check if user is suspended in the period the revision was made
            if ignore_suspension_period is False and self.user().suspended_since is not None:
                if revision.utc >= self.user().suspended_since:
                    logger.debug('Skipping revision %s in suspension period', revision.revid)
                    continue

            # Add revision points
            for contrib in self.get(revision=revision):
                if ignore_max:
                    points += contrib.raw_points
                else:
                    points += contrib.points

            # Subtract point deductions
            if not ignore_point_deductions:
                for deduction in revision.point_deductions:
                    logger.debug('Subtracting %.1f points from point deduction', deduction[0])
                    points -= deduction[0]
        
        return points

        # p = 0.
        # for revid, rev in self.revisions.items():
        #     dt = pytz.utc.localize(datetime.fromtimestamp(rev.timestamp))
        #     if ignore_suspension_period is True or self.user().suspended_since is None or dt < self.user().suspended_since:
        #         p += rev.get_points(ptype, ignore_max, ignore_point_deductions)
        #     else:
        #         logger.debug('!! Skipping revision %d in suspension period', revid)

    def get_articles(self):
        return sorted(list(set([contrib.article for contrib in self.contributions])), key=lambda article: article.name)

    def sum(self):
        return sum([self.get_article_points(article) for article in self.get_articles()])

    def summarize(self, wiki_tz):
        articles = self.get_articles()

        articles_formatted = []

        for article in articles:
            article_contribs = self.get(article=article)
            revisions = set([contrib.rev for contrib in article_contribs])
            revisions_formatted = []
            for revision in revisions:
                revision_formatted = self.summarize_revision(revision)
                if revision_formatted is not None:
                    revisions_formatted.append(revision_formatted)

            article_formatted = self.summarize_article(article, revision_formatted)

            articles_formatted.append(article_formatted)
        
        return articles_formatted

    def summarize_revision(self, revision):

        revision_contribs = filter(lambda c: not is_zero(c.points), self.get(revision=revision))

        if len(revision_contribs) == 0:
            return None

        formatted = '[%s %s]: ' % (revision.get_link(), revision.wiki_tz.strftime(_('%A, %H:%M')))

        # Make a formatted string on this form:
        # 10.0 p (ny side) + 9.7 p (967 byte) + 5.4 p (54 ord) + 10.0 p (2 kilder)
        contrib_points = []
        for contribution in revision_contribs:
            contrib_points.append('%.1f p (%s)' % (contribution.points, contribution.description))
        formatted += ' + '.join(contrib_points)
        
        # Add deductions, if any
        for deduction in revision.point_deductions:
            if deduction[0] > 0:
                formatted += ' <span style="color:red">− %.1f p (%s)</span>' % (deduction[0], deduction[1])
            else:
                formatted += ' <span style="color:green">+ %.1f p (%s)</span>' % (- deduction[0], deduction[1])

        # Strikeout if revision was in suspended period
        if self.user().suspended_since is not None and revision.utc > self.user().suspended_since:
            formatted = '<s>' + formatted + '</s>'

        # Add warning icon if revision has errors
        if len(revision.errors) > 0:
            formatted = '[[File:Ambox warning yellow.svg|12px|%s]] ' % (', '.join(revision.errors)) + formatted

        return formatted

    def summarize_article(self, article, revisions_formatted):

        brutto = self.get_article_points(article, ignore_suspension_period=True, ignore_point_deductions=True,
                                         ignore_disqualification=True)
        netto = self.get_article_points(article)

        # if brutto == 0.0:
        #     logger.debug('    %s: skipped (0 points)', article.key)
        #     continue

        # for contrib in contribs:

        tooltip_text = ''
        try:
            cat_path = [x.split(':')[-1] for x in article.cat_path]
            tooltip_text = "''" + _('Category hit') + "'': " + ' &gt; '.join(cat_path) + '<br />'
        except AttributeError:
            pass
        tooltip_text += '<br />'.join(revisions_formatted)

        # if len(article.point_deductions) > 0:
        #     pds = []
        #     for points, reason in article.point_deductions:
        #         pds.append('%.f p: %s' % (-points, reason))
        #     titletxt += '<div style="border-top:1px solid #CCC">\'\'' + _('Notes') + ':\'\'<br />%s</div>' % '<br />'.join(pds)

        tooltip_text += '<div style="border-top:1px solid #CCC">' + _('Total: {{formatnum:%(bytecount)d}} bytes, %(wordcount)d words') % {
            'bytecount': article.bytes,
            'wordcount': article.words
        } + '.</div>'

        p = '%.1f p' % brutto
        if brutto != netto:
            p = '<s>' + p + '</s> '
            if netto != 0.:
                p += '%.1f p' % netto

        formatted = '[[%s|%s]]' % (article.link(), article.name)
        if article.key in self.user().disqualified_articles:
            formatted = '[[File:Qsicon Achtung.png|14px]] <s>' + formatted + '</s>'
            tooltip_text += '<div style="border-top:1px solid red; background:#ffcccc;">' + _('<strong>Note:</strong> The contributions to this article are currently disqualified.') + '</div>'
        elif brutto != netto:
            formatted = '[[File:Qsicon Achtung.png|14px]] ' + formatted
            #titletxt += '<div style="border-top:1px solid red; background:#ffcccc;"><strong>Merk:</strong> En eller flere revisjoner er ikke talt med fordi de ble gjort mens brukeren var suspendert. Hvis suspenderingen oppheves vil bidragene telle med.</div>'

        if article.new:
            formatted += ' ' + _('<abbr class="newpage" title="New page">N</abbr>')

        formatted += ' (<abbr class="uk-ap">%s</abbr>)' % article_points

        formatted = '# ' + formatted
        formatted += '<div class="uk-ap-title" style="font-size: smaller; color:#888; line-height:100%;">' + tooltip_text + '</div>'

        logger.debug('    %s: %.f / %.f points', article.key, netto, brutto)

        return formatted


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


    # def get_points(self, ptype='', ignore_max=False, ignore_point_deductions=False):
    #     p = 0.0
    #     for pnt in self.points:
    #         if ptype == '' or pnt[1] == ptype:
    #             if ignore_max and len(pnt) > 3:
    #                 p += pnt[3]
    #             else:
    #                 p += pnt[0]

    #     if not ignore_point_deductions and (ptype == '' or ptype == 'trekk'):
    #         for points, reason in self.point_deductions:
    #             p -= points

    #     return p
