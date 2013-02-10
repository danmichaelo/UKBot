# Makefile for various po files.
 
# Add more languages here!  Beware that this is a makefile snippet and
# you have to adhere to make syntax.
LINGUAS = nb_NO \
	  fi_FI \

# Textdomain for our package.
TEXTDOMAIN = messages
 
# Initial copyright holder added to pot and po files.
#COPYRIGHT_HOLDER = Guido Flohr
COPYRIGHT_HOLDER = Dan Michael
 
# Where to send msgid bugs?  
#MSGID_BUGS_ADDRESS = Guido Flohr <guido@imperia.net>
MSGID_BUGS_ADDRESS = danm

srcdir = .
libdir = .
 
#CATALOGS = $(addsuffix .po, LINGUAS)
CATALOGS = $(LINGUAS)
MO_FILES = $(addsuffix .mo, $(LINGUAS))
 
MSGMERGE = msgmerge
MSGFMT   = msgfmt
XGETTEXT = xgettext
CATOBJEXT = .po
 
TD = $(strip $(TEXTDOMAIN))
 
default: help
 
all: $(TD).pot update-po update-mo install makedb
 
help:
	@echo "Available targets:"
	@echo "  pot                       - remake master catalog"
	@echo "  update-po                 - merge po files"
	@echo "  update-mo                 - regenerate mo files"
	@echo "  install                   - install mo files"
	@echo "  all               - all of the above"
 
POTFILES = $(srcdir)/POTFILES.in \
	$(shell cat $(srcdir)/POTFILES.in) 
 
pot: $(TD).pot 

clean:
	rm -f *~ *.bak *.mo
 
# FIXME: The parameter --from-code is only needed if your sources contain
# any 8 bit data (even in comments).  UTF-8 is only a guess here, but it
# will at least accept any 8 bit data.
#
# The parameter "--language=perl" is not strictly needed because the
# source language of all our files will be auto-detected by xgettext
# by their filename extension.  You should even avoid this parameter
# if you want to extract strings from multiple source languages.
$(TD).pot: $(POTFILES)
	$(XGETTEXT) --output=$(srcdir)/$(TD).pox \
		--files-from=$(srcdir)/POTFILES.in
	rm -f $@ && mv $(TD).pox $@
 
install: $(MO_FILES)
	cd $(srcdir); \
	targetdir='$(libdir)/locale'; \
	languages='$(LINGUAS)'; \
	for lang in $$languages; do \
		mkdir -p "$$targetdir/$$lang/LC_MESSAGES" || exit 1; \
		dest="$$targetdir/$$lang/LC_MESSAGES/$(TD).mo"; \
		cat="$$lang.mo"; \
		echo "installing $$cat as $$dest"; \
		cp -f $$cat $$dest && chmod 644 $$dest || exit 1; \
	done
 
update-mo: $(MO_FILES)
 
update-po:
	$(MAKE) $(TD).pot
	cd $(srcdir); \
		catalogs='$(CATALOGS)'; \
		for cat in $$catalogs; do \
		  cat=`basename $$cat`; \
		  lang=`echo $$cat | sed 's/\$(CATOBJEXT)$$//'`; \
		  mv $$lang.po $$lang.old.po; \
		  echo "$$lang:"; \
		  if $(MSGMERGE) $$lang.old.po $(TD).pot -o $$lang.po; then \
			rm -f $$lang.old.po; \
		  else \
			echo "msgmerge for $$cat failed!"; \
			rm -f $$lang.po; \
			mv $$lang.old.po $$lang.po; \
		  fi; \
		done
 
.SUFFIXES:
.SUFFIXES: .po .mo
 
.po.mo:
	$(MSGFMT) --verbose -o $@ $<

#	$(MSGFMT) --check --statistics --verbose -o $@ $<


makedb:
	./db/initialize.sh


#MSGSRC=$(wildcard locale/*/LC_MESSAGES/messages.po)
#MSGOBJ=$(addprefix $(TARGET_BUILD_PATH)/$(target)/,$(MSG_SRC:.po=.mo))

#gettext: $(MSGOBJS)

#locale/%/LC_MESSAGES/messages.mo: locale/%/LC_MESSAGES/messages.po
#	msgfmt -c $< -o $@


#.PHONY: makedb
