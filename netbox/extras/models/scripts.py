import inspect
import logging
from functools import cached_property

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from core.choices import ManagedFileRootPathChoices
from core.models import ManagedFile
from extras.utils import is_script
from netbox.models.features import JobsMixin, EventRulesMixin
from utilities.querysets import RestrictedQuerySet
from .mixins import PythonModuleMixin

__all__ = (
    'Script',
    'ScriptModule',
)

logger = logging.getLogger('netbox.data_backends')


class Script(EventRulesMixin, JobsMixin, models.Model):
    name = models.CharField(
        verbose_name=_('name'),
        max_length=79,
    )
    module = models.ForeignKey(
        to='extras.ScriptModule',
        on_delete=models.PROTECT,
        related_name='scripts'
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name', 'pk')
        constraints = (
            models.UniqueConstraint(
                fields=('name', 'module'),
                name='%(app_label)s_%(class)s_unique_name_module'
            ),
        )
        verbose_name = _('script')
        verbose_name_plural = _('scripts')

    @cached_property
    def python_class(self):
        return self.module.get_module_scripts.get(self.name)

    def get_jobs(self):
        return self.module.jobs.filter(
            name=self.name
        )


class ScriptModuleManager(models.Manager.from_queryset(RestrictedQuerySet)):

    def get_queryset(self):
        return super().get_queryset().filter(file_root=ManagedFileRootPathChoices.SCRIPTS)


class ScriptModule(PythonModuleMixin, JobsMixin, ManagedFile):
    """
    Proxy model for script module files.
    """
    objects = ScriptModuleManager()

    class Meta:
        proxy = True
        verbose_name = _('script module')
        verbose_name_plural = _('script modules')

    def get_absolute_url(self):
        return reverse('extras:script_list')

    def __str__(self):
        return self.python_name

    @cached_property
    def get_module_scripts(self):

        def _get_name(cls):
            # For child objects in submodules use the full import path w/o the root module as the name
            return cls.full_name.split(".", maxsplit=1)[1]

        try:
            module = self.get_module()
        except Exception as e:
            logger.debug(f"Failed to load script: {self.python_name} error: {e}")
            module = None

        scripts = {}
        ordered = getattr(module, 'script_order', [])

        for cls in ordered:
            scripts[_get_name(cls)] = cls
        for name, cls in inspect.getmembers(module, is_script):
            if cls not in ordered:
                scripts[_get_name(cls)] = cls

        return scripts

    def save(self, *args, **kwargs):
        self.file_root = ManagedFileRootPathChoices.SCRIPTS
        return super().save(*args, **kwargs)
