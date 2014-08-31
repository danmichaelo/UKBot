# Makefile for various po files.
 
# Add more languages here!  Beware that this is a makefile snippet and
# you have to adhere to make syntax.
LINGUAS = nb_NO \
	  fi_FI \

# Textdomain for our package.
TEXTDOMAIN = messages

srcdir = ./bot
 
CATALOGS = $(LINGUAS)
MO_FILES = $(addprefix $(srcdir)/, $(addsuffix .mo, $(LINGUAS)))
 
MSGMERGE = msgmerge
MSGFMT   = msgfmt
XGETTEXT = xgettext
CATOBJEXT = .po
 
TD = $(strip $(TEXTDOMAIN))
 
default: help
 
all: $(TD).pot update-po update-mo install 
# makedb
 
help:
	@echo "Available targets:"
	@echo "  pot          - Regenerate master catalog from source files"
	@echo "  update-po    - Update po files from master catalog"
	@echo "  update-mo    - Regenerate mo files from po files"
	@echo "  install      - Install mo files"
	@echo "  all          - All of the above"
 
POTFILES = $(srcdir)/POTFILES.in \
	$(shell cat $(srcdir)/POTFILES.in) 
 
pot: $(TD).pot 

clean:
	for dir in ./ ./bot; do \
		rm -fv $$dir/*~ $$dir/*.bak $$dir/*.mo $$dir/*.pox $$dir/*.pot; \
	done


# Use xgettext to extract strings from the source code
# files listed in POTFILESS.in

$(TD).pot: $(POTFILES)
	$(XGETTEXT) --output=$(srcdir)/$(TD).pox \
		--files-from=$(srcdir)/POTFILES.in
	rm -f $(srcdir)/$@ && mv $(srcdir)/$(TD).pox $(srcdir)/$@
 
install: $(MO_FILES)
	targetdir='./bot/locale'; \
	languages='$(LINGUAS)'; \
	for lang in $$languages; do \
		mkdir -p "$$targetdir/$$lang/LC_MESSAGES" || exit 1; \
		dest="$$targetdir/$$lang/LC_MESSAGES/$(TD).mo"; \
		cat="$(srcdir)/$$lang.mo"; \
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


#makedb:
#	./db/initialize.sh


#MSGSRC=$(wildcard locale/*/LC_MESSAGES/messages.po)
#MSGOBJ=$(addprefix $(TARGET_BUILD_PATH)/$(target)/,$(MSG_SRC:.po=.mo))

#gettext: $(MSGOBJS)

#locale/%/LC_MESSAGES/messages.mo: locale/%/LC_MESSAGES/messages.po
#	msgfmt -c $< -o $@


#.PHONY: makedb
