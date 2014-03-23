



def hello_vk():
    return 'Hello World2!'



url_map = Map([
    Rule('/', endpoint='get_index'),
    Rule('/<lang>/', endpoint='get_uk_list'),
    Rule('/<lang>/contest/<week>', endpoint='get_uk_contest_details'),
    Rule('/<lang>/user/<user>', endpoint='get_uk_user_details'),
    ], default_subdomain='tools')


def application(environ, start_response):
    #logger.info(environ)
    environ['SCRIPT_NAME'] = '/ukbot'
    try:
        urls = url_map.bind_to_environ(environ, server_name='wmflabs.org', subdomain='tools')
        endpoint, args = urls.match()
        logger.info(args)
        response = globals()[endpoint](args)
        return response(environ, start_response)
    except NotFound, e:
        response = error_404()
        return response(environ, start_response)
    except RequestRedirect, e:
        logger.info('Redir to: %s' % e.new_url)
        response = redirect(e.new_url)
        return response(environ, start_response)

    except HTTPException, e:
        logger.error(e)
        return e(environ, start_response)
    #logger.info(args)
    #return ['Rule points to %r with arguments %r' % (endpoint, args)]


#try:
#    CGIHandler().run(application)
#except Exception as e:
#    logger.exception('Unhandled Exception')
