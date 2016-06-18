import json
import operator
import os
import random
from collections import namedtuple
from datetime import date, datetime
from functools import wraps
from passlib.hash import pbkdf2_sha256

from flask import Flask, request, session, redirect, url_for, abort, render_template, Response
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.markdown import Markdown
from sqlalchemy import cast, types
from sqlalchemy.sql import func, label, desc

if os.environ.get('HEROKU') == '1':
    db_uri = os.environ['DATABASE_URL']
    skey = os.environ['SECRET_KEY']
else:
    # development environment
    db_uri = 'sqlite:///db.sqlite3'
    skey = '57c4bcb7897eefa75f0d791dd06bcfa1'

app = Flask(__name__)
app.config.update(dict(
    SQLALCHEMY_DATABASE_URI=db_uri,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=skey,
))

Markdown(app)
db = SQLAlchemy(app)


class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return '<Group %s>' % self.name


class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String)
    creator = db.Column(db.String)
    notes = db.Column(db.String)

    date_added = db.Column(db.Date)

    group_id = db.Column(db.Integer, db.ForeignKey('group.id'))
    group = db.relationship('Group',
                            backref=db.backref(
                                'entries', lazy='dynamic', cascade='delete')
                            )

    def __init__(self, title, creator, notes, group):
        self.title = title
        self.creator = creator
        self.notes = notes
        self.group = group
        self.date_added = date.today()

    def __repr__(self):
        return '<Entry \'{}\'>'.format(self.title)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    level = db.Column(db.Integer)
    passhash = db.Column(db.String)

    READ = 1
    WRITE = 2
    ADMIN = 3

    def __init__(self, name, password, level):
        self.name = name
        self.passhash = pbkdf2_sha256.encrypt(password)
        self.level = level

    def __repr__(self):
        return '<User \'{}\', {}>'.format(self.name, self.level)

    def check_pass(self, password):
        return pbkdf2_sha256.verify(password, self.passhash)


def login_required(level):
    def login_decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('user'):
                if session['user']['level'] < level:
                    abort(401)
            else:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return login_decorator


def check_params(*reqd):
    for param in reqd:
        if not request.form[param]:
            abort(400)
    return request.form


@app.context_processor
def context_processor():
    def is_writer():
        return session['user']['level'] >= User.WRITE

    def is_admin():
        return session['user']['level'] >= User.ADMIN

    return {'is_writer': is_writer, 'is_admin': is_admin}


def notes_transform(n):
    subs = [(' -- ', u' \u2013 '), ('->', u'\u2192')]
    for a, b in subs:
        n = n.replace(a, b)
    return n


# main app pages

@app.route('/')
@login_required(User.READ)
def all_groups():
    groups = Group.query.all()
    groups.sort(key=lambda g: g.entries.count(), reverse=True)
    return render_template('all_groups.html', groups=groups)


@app.route('/group/<int:group_id>/')
@login_required(User.READ)
def group_detail(group_id):
    return render_template('group_detail.html', group=Group.query.get_or_404(group_id))


@app.route('/entry/<int:entry_id>')
@login_required(User.READ)
def entry_detail(entry_id):
    return render_template('entry_detail.html', entry=Entry.query.get_or_404(entry_id))


@app.route('/group/new', methods=['POST'])
@login_required(User.ADMIN)
def new_group():
    param = check_params('name')

    g = Group(param['name'])
    db.session.add(g)
    db.session.commit()

    return redirect(url_for('all_groups'))


@app.route('/group/<int:group_id>/new', methods=['GET', 'POST'])
@login_required(User.WRITE)
def new_entry(group_id):
    g = Group.query.get_or_404(group_id)

    if request.method == 'POST':
        params = check_params('title', 'creator', 'notes')

        notes = notes_transform(params['notes'])
        e = Entry(params['title'], params['creator'], notes, g)
        db.session.add(e)
        db.session.commit()

        return redirect(url_for('entry_detail', entry_id=e.id))

    return render_template('new_entry.html', group=g)


@app.route('/entry/<int:entry_id>/edit', methods=['GET', 'POST'])
@login_required(User.WRITE)
def edit_entry(entry_id):
    e = Entry.query.get_or_404(entry_id)

    if request.method == 'POST':
        params = check_params('title', 'creator', 'notes')

        e.title = params['title']
        e.creator = params['creator']
        e.notes = notes_transform(params['notes'])

        db.session.commit()

        return redirect(url_for('entry_detail', entry_id=e.id))

    return render_template('edit_entry.html', entry=e)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        params = check_params('username', 'password')

        user = User.query.filter_by(name=params['username']).first()
        if user:
            if user.check_pass(params['password']):
                # session data needs to be JSON-serializable
                session['user'] = {'name': user.name, 'level': user.level}
                return redirect(url_for('all_groups'))
            else:
                error = 'Wrong password!'
        else:
            error = 'No such user'

    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


@app.route('/group/<int:group_id>/study/', methods=['GET'])
@login_required(User.READ)
def study(group_id):
    return render_template('study.html', group=Group.query.get_or_404(group_id))


@app.route('/group/<int:group_id>/study/q')
@login_required(User.READ)
def get_questions(group_id):
    contents = []
    entries = Entry.query.filter_by(group_id=group_id).order_by(
        func.random()).limit(10).all()
    for e in entries:
        lines = e.notes.split('---')[0].split('\n')
        for i in xrange(0, 10):
            # strip leading spaces & bullets
            line = random.choice(lines).lstrip(' +')
            if (len(line) >= 16) or ('**' in line):
                contents.append({
                    'id': e.id,
                    'title': e.title,
                    'creator': e.creator,
                    'clue': line
                })
                break

    return json.dumps(contents)


@app.route('/group/<int:group_id>/search')
@login_required(User.READ)
def search(group_id):
    g = Group.query.get_or_404(group_id)
    query = request.args['q']
    if not query:
        return redirect(url_for('group_detail', group_id=group_id))
    results = Entry.query.filter(
        Entry.group_id == group_id, Entry.notes.ilike('%{}%'.format(query)))
    return render_template('search.html', group=g, results=results, query=query)


@app.route('/group/<int:group_id>/stats')
@login_required(User.READ)
def stats(group_id):
    g = Group.query.get_or_404(group_id)

    s = dict()
    Histogram = namedtuple('Histogram', ['data', 'maxval'])

    creators = (
        db.session.query(
            Entry.creator,
            func.count(Entry.id).label('nworks')
        )
        .filter(Entry.group_id == group_id)
        .group_by(Entry.creator)
    )

    s['nworks'] = g.entries.count()
    s['ncreators'] = creators.count()
    s['nworks_top'] = creators.order_by(desc('nworks')).limit(20).all()

    creators = creators.subquery()
    nworks_data = db.session.query(
        creators.c.nworks,
        func.count(creators.c.nworks)
    ).group_by(creators.c.nworks).all()
    nworks_max = max(map(operator.itemgetter(1), nworks_data))
    s['nworks_hist'] = Histogram(nworks_data, nworks_max)

    dateformat = cast(func.extract('year', Entry.date_added), types.String) + \
        '-' + cast(func.extract('month', Entry.date_added), types.String)
    months_data = (
        db.session.query(dateformat, func.count(Entry.id))
        .filter(Entry.group_id == group_id)
        .group_by(
            cast(func.extract('year', Entry.date_added), types.Integer),
            cast(func.extract('month', Entry.date_added), types.Integer)
        )
        .all()
    )
    months_max = max(map(operator.itemgetter(1), months_data))
    s['months_hist'] = Histogram(months_data, months_max)

    lengths_data = (
        db.session.query(
            func.length(Entry.notes) / 200 * 200,
            func.count(Entry.id)
        )
        .filter(Entry.group_id == group_id)
        .group_by(func.length(Entry.notes) / 200).all()
    )
    lengths_max = max(map(operator.itemgetter(1), lengths_data))
    s['lengths_hist'] = Histogram(lengths_data, lengths_max)

    lengths = db.session.query(
        Entry.title,
        func.length(Entry.notes).label("length")
    ).filter(Entry.group_id == group_id).order_by(desc("length")).all()
    s['longest'] = lengths[:16]
    s['shortest'] = reversed(lengths[-16:])
    s['total_len'] = sum(map(operator.itemgetter(1), lengths))
    s['avg_len'] = 1.0 * s['total_len'] / s['nworks']

    return render_template('stats.html', group=g, stats=s)


@app.route('/group/<int:group_id>/delete', methods=['POST'])
@login_required(User.ADMIN)
def delete_group(group_id):
    g = Group.query.get_or_404(group_id)
    db.session.delete(g)
    db.session.commit()
    return redirect(url_for('all_groups'))


@app.route('/download')
@login_required(User.READ)
def download():
    obj = {}
    for g in Group.query.all():
        obj[g.name] = {}
        for e in g.entries.all():
            obj[g.name][e.title] = {
                'creator': e.creator,
                'notes': e.notes,
                'date': str(e.date_added)
            }

    headers = {'Content-Disposition': 'inline; filename="qbnotes.json"'}
    return Response(json.dumps(obj, indent=4, separators=(',', ': ')),
                    mimetype='text/json', headers=headers)


@app.route('/upload', methods=['POST'])
@login_required(User.ADMIN)
def upload():
    if request.files['file']:
        try:
            doc = json.loads(request.files['file'].read())
            for group_name in doc:
                group = Group.query.filter(Group.name == group_name).first()
                if not group:
                    group = Group(group_name)
                    db.session.add(group)

                for title in doc[group_name]:
                    obj = doc[group_name][title]

                    entry = Entry.query.filter(
                        Entry.title == title,
                        Entry.creator == obj['creator']
                    ).first()

                    if entry:
                        entry.notes = obj['notes']
                    else:
                        new = Entry(title, obj['creator'], obj['notes'], group)
                        db.session.add(new)

            db.session.commit()
        except ValueError:
            pass

    return redirect(url_for('all_groups'))


if __name__ == '__main__':
    db.create_all()
    app.run(host='0.0.0.0', debug=True, port=5001)
