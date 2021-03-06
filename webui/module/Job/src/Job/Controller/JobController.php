<?php

/**
 *
 * bareos-webui - Bareos Web-Frontend
 *
 * @link      https://github.com/bareos/bareos-webui for the canonical source repository
 * @copyright Copyright (c) 2013-2017 Bareos GmbH & Co. KG (http://www.bareos.org/)
 * @license   GNU Affero General Public License (http://www.gnu.org/licenses/)
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 */

namespace Job\Controller;

use Zend\Mvc\Controller\AbstractActionController;
use Zend\View\Model\ViewModel;
use Zend\Json\Json;
use Job\Form\JobForm;
use Job\Form\RunJobForm;
use Job\Model\Job;

class JobController extends AbstractActionController
{

   protected $jobModel = null;
   protected $clientModel = null;
   protected $filesetModel = null;
   protected $storageModel = null;
   protected $poolModel = null;
   protected $bsock = null;
   protected $acl_alert = false;

   private $required_commands = array(
      "list",
      "llist",
      "rerun",
      "cancel",
      "run",
      "enable",
      "disable",
      ".jobs"
   );

   public function indexAction()
   {
      $this->RequestURIPlugin()->setRequestURI();

      if(!$this->SessionTimeoutPlugin()->isValid()) {
         return $this->redirect()->toRoute('auth', array('action' => 'login'), array('query' => array('req' => $this->RequestURIPlugin()->getRequestURI(), 'dird' => $_SESSION['bareos']['director'])));
      }

      if(!$this->CommandACLPlugin()->validate($_SESSION['bareos']['commands'], $this->required_commands)) {
         $this->acl_alert = true;
         return new ViewModel(
            array(
               'acl_alert' => $this->acl_alert,
               'required_commands' => $this->required_commands,
            )
         );
      }

      $period = $this->params()->fromQuery('period') ? $this->params()->fromQuery('period') : '7';
      $status = $this->params()->fromQuery('status') ? $this->params()->fromQUery('status') : 'all';
      $jobname = $this->params()->fromQuery('jobname') ? $this->params()->fromQUery('jobname') : 'all';

      try {
         $this->bsock = $this->getServiceLocator()->get('director');
         $jobs = $this->getJobModel()->getJobsByType($this->bsock, null);
         array_push($jobs, array('name' => 'all'));
      }
      catch(Exception $e) {
         echo $e->getMessage();
      }

      $form = new JobForm($jobs, $jobname, $period, $status);

      $action = $this->params()->fromQuery('action');
      if(empty($action)) {
         return new ViewModel(
            array(
               'form' => $form,
               'status' => $status,
               'period' => $period,
               'jobname' => $jobname
            )
         );
      }
      else {
         try {
            $this->bsock = $this->getServiceLocator()->get('director');
         }
         catch(Exception $e) {
            echo $e->getMessage();
         }

         if($action == "rerun") {
            $jobid = $this->params()->fromQuery('jobid');

            $result = null;
            try {
               $result = $this->getJobModel()->rerunJob($this->bsock, $jobid);
            }
            catch(Exception $e) {
               echo $e->getMessage();
            }
         }

         try {
            $this->bsock->disconnect();
         }
         catch(Exception $e) {
            echo $e->getMessage();
         }

         return new ViewModel(
            array(
               'form' => $form,
               'status' => $status,
               'period' => $period,
               'jobname' => $jobname,
               'result' => $result
            )
         );
      }
   }

   public function detailsAction()
   {
      $this->RequestURIPlugin()->setRequestURI();

      if(!$this->SessionTimeoutPlugin()->isValid()) {
         return $this->redirect()->toRoute('auth', array('action' => 'login'), array('query' => array('req' => $this->RequestURIPlugin()->getRequestURI(), 'dird' => $_SESSION['bareos']['director'])));
      }

      if(!$this->CommandACLPlugin()->validate($_SESSION['bareos']['commands'], $this->required_commands)) {
         $this->acl_alert = true;
         return new ViewModel(
            array(
               'acl_alert' => $this->acl_alert,
               'required_commands' => $this->required_commands,
            )
         );
      }

      $jobid = (int) $this->params()->fromRoute('id', 0);

      try {
         $this->bsock = $this->getServiceLocator()->get('director');
         //$job = $this->getJobModel()->getJob($this->bsock, $jobid);
         //$joblog = $this->getJobModel()->getJobLog($this->bsock, $jobid);
         $this->bsock->disconnect();
      }
      catch(Exception $e) {
         echo $e->getMessage();
      }

      return new ViewModel(array(
         //'job' => $job,
         //'joblog' => $joblog,
         'jobid' => $jobid
      ));
   }

   public function cancelAction()
   {
      $this->RequestURIPlugin()->setRequestURI();

      if(!$this->SessionTimeoutPlugin()->isValid()) {
         return $this->redirect()->toRoute('auth', array('action' => 'login'), array('query' => array('req' => $this->RequestURIPlugin()->getRequestURI(), 'dird' => $_SESSION['bareos']['director'])));
      }

      $result = null;

      $jobid = (int) $this->params()->fromRoute('id', 0);

      try {
         $this->bsock = $this->getServiceLocator()->get('director');
         $result = $this->getJobModel()->cancelJob($this->bsock, $jobid);
         $this->bsock->disconnect();
      }
      catch(Exception $e) {
         echo $e->getMessage();
      }

      return new ViewModel(
         array(
            'bconsoleOutput' => $result
         )
      );
   }

   public function actionsAction()
   {
      $this->RequestURIPlugin()->setRequestURI();

      if(!$this->SessionTimeoutPlugin()->isValid()) {
         return $this->redirect()->toRoute('auth', array('action' => 'login'), array('query' => array('req' => $this->RequestURIPlugin()->getRequestURI(), 'dird' => $_SESSION['bareos']['director'])));
      }

      if(!$this->CommandACLPlugin()->validate($_SESSION['bareos']['commands'], $this->required_commands)) {
         $this->acl_alert = true;
         return new ViewModel(
            array(
               'acl_alert' => $this->acl_alert,
               'required_commands' => $this->required_commands,
            )
         );
      }

      $result = null;

      $action = $this->params()->fromQuery('action');

      if(empty($action)) {
         return new ViewModel();
      }
      else {
         try {
            $this->bsock = $this->getServiceLocator()->get('director');
         }
         catch(Exception $e) {
            echo $e->getMessage();
         }

         if($action == "queue") {
            $jobname = $this->params()->fromQuery('job');
            try {
               $result = $this->getJobModel()->runJob($this->bsock, $jobname);
            }
            catch(Exception $e) {
               echo $e->getMessage();
            }
         }
         elseif($action == "enable") {
            $jobname = $this->params()->fromQuery('job');
            try {
               $result = $this->getJobModel()->enableJob($this->bsock, $jobname);
            }
            catch(Exception $e) {
               echo $e->getMessage();
            }
         }
         elseif($action == "disable") {
            $jobname = $this->params()->fromQuery('job');
            try {
               $result = $this->getJobModel()->disableJob($this->bsock, $jobname);
            }
            catch(Exception $e) {
               echo $e->getMessage();
            }
         }

         try {
            $this->bsock->disconnect();
         }
         catch(Exception $e) {
            echo $e->getMessage();
         }

         return new ViewModel(
            array(
               'result' => $result
            )
         );
      }
   }

   public function runAction()
   {
      $this->RequestURIPlugin()->setRequestURI();

      if(!$this->SessionTimeoutPlugin()->isValid()) {
         return $this->redirect()->toRoute('auth', array('action' => 'login'), array('query' => array('req' => $this->RequestURIPlugin()->getRequestURI(), 'dird' => $_SESSION['bareos']['director'])));
      }

      if(!$this->CommandACLPlugin()->validate($_SESSION['bareos']['commands'], $this->required_commands)) {
         $this->acl_alert = true;
         return new ViewModel(
            array(
               'acl_alert' => $this->acl_alert,
               'required_commands' => $this->required_commands,
            )
         );
      }

      $this->bsock = $this->getServiceLocator()->get('director');

      // Get query parameter jobname
      $jobname = $this->params()->fromQuery('jobname') ? $this->params()->fromQuery('jobname') : null;

      if ($jobname != null) {
         $jobdefaults = $this->getJobModel()->getJobDefaults($this->bsock, $jobname);
      }

      // Get required form construction data, jobs, clients, etc.
      $clients = $this->getClientModel()->getClients($this->bsock);

      // Get the different kind of jobs and merge them. Jobs of the following types
      // cannot nor wanted to be run. M,V,R,U,I,C and S.
      $job_type_B = $this->getJobModel()->getJobsByType($this->bsock, "B"); // Backup Job
      $job_type_D = $this->getJobModel()->getJobsByType($this->bsock, 'D'); // Admin Job
      $job_type_A = $this->getJobModel()->getJobsByType($this->bsock, 'A'); // Archive Job
      $job_type_c = $this->getJobModel()->getJobsByType($this->bsock, 'c'); // Copy Job
      $job_type_g = $this->getJobModel()->getJobsByType($this->bsock, 'g'); // Migration Job
      $job_type_O = $this->getJobModel()->getJobsByType($this->bsock, 'O'); // Always Incremental Consolidate Job
      $job_type_V = $this->getJobModel()->getJobsByType($this->bsock, 'V'); // Verify Job

      $jobs = array_merge($job_type_B, $job_type_D, $job_type_A, $job_type_c, $job_type_g, $job_type_O, $job_type_V);

      $filesets = $this->getFilesetModel()->getDotFilesets($this->bsock);
      $storages = $this->getStorageModel()->getStorages($this->bsock);
      $pools = $this->getPoolModel()->getDotPools($this->bsock, null);

      // build form
      $form = new RunJobForm($clients, $jobs, $filesets, $storages, $pools, $jobdefaults);

      // Set the method attribute for the form
      $form->setAttribute('method', 'post');

      // result
      $result = null;
      $errors = null;

      $request = $this->getRequest();

      if($request->isPost()) {

         $job = new Job();
         $form->setInputFilter($job->getInputFilter());
         $form->setData($request->getPost());

         if($form->isValid()) {

            $jobname = $form->getInputFilter()->getValue('job');
            $client = $form->getInputFilter()->getValue('client');
            $fileset = $form->getInputFilter()->getValue('fileset');
            $storage = $form->getInputFilter()->getValue('storage');
            $pool = $form->getInputFilter()->getValue('pool');
            $level = $form->getInputFilter()->getValue('level');
            $priority = $form->getInputFilter()->getValue('priority');
            $backupformat = null; // $form->getInputFilter()->getValue('backupformat');
            $when = $form->getInputFilter()->getValue('when');

            try {
               $result = $this->getJobModel()->runCustomJob($this->bsock, $jobname, $client, $fileset, $storage, $pool, $level, $priority, $backupformat, $when);
               $this->bsock->disconnect();
               $s = strrpos($result, "=") + 1;
               $jobid = rtrim( substr( $result, $s ) );
               return $this->redirect()->toRoute('job', array('action' => 'details', 'id' => $jobid));
            }
            catch(Exception $e) {
               echo $e->getMessage();
            }
         }
         else {
            $this->bsock->disconnect();
            return new ViewModel(array(
               'form' => $form,
               'result' => $result,
               'errors' => $errors
            ));
         }
      }
      else {
         $this->bsock->disconnect();
         return new ViewModel(array(
            'form' => $form,
            'result' => $result,
            'errors' => $errors
         ));
      }
   }

   public function getDataAction()
   {
      $this->RequestURIPlugin()->setRequestURI();

      if(!$this->SessionTimeoutPlugin()->isValid()) {
         return $this->redirect()->toRoute('auth', array('action' => 'login'), array('query' => array('req' => $this->RequestURIPlugin()->getRequestURI(), 'dird' => $_SESSION['bareos']['director'])));
      }

      $result = null;

      $data = $this->params()->fromQuery('data');
      $jobid = $this->params()->fromQuery('jobid');
      $jobname = $this->params()->fromQuery('jobname');
      $status = $this->params()->fromQuery('status');
      $period = $this->params()->fromQuery('period');

      try {
         $this->bsock = $this->getServiceLocator()->get('director');
      }
      catch(Exception $e) {
         echo $e->getMessage();
      }

      if($data == "jobs" && $status == "all") {
         try {
            $result = $this->getJobModel()->getJobs($this->bsock, $jobname, $period);
         }
         catch(Exception $e) {
            echo $e->getMessage();
         }
      }
      elseif($data == "jobs" && $status == "successful") {
         try {
            $jobs_T = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'T', $period, null); // Terminated
            $result = $jobs_T;
         }
         catch(Exception $e) {
            echo $e->getMessage();
         }
      }
      elseif($data == "jobs" && $status == "warning") {
         try {
            $jobs_A = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'A', $period, null); // Terminated
            $jobs_W = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'W', $period, null); // Terminated with warnings
            $result = array_merge($jobs_A, $jobs_W);
         }
         catch(Exception $e) {
            echo $e->getMessage();
         }
      }
      elseif($data == "jobs" && $status == "unsuccessful") {
         try {
            $jobs_E = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'E', $period, null); //
            $jobs_e = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'e', $period, null); //
            $jobs_f = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'f', $period, null); //
            $result = array_merge($jobs_E, $jobs_e, $jobs_f);
         }
         catch(Exception $e) {
            echo $e->getMessage();
         }
      }
      elseif($data == "jobs" && $status == "running") {
         try {
            $jobs_R = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'R', $period, null);
            $jobs_l = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'l', $period, null);
            $result = array_merge($jobs_R, $jobs_l);
         }
         catch(Exception $e) {
            echo $e->getMessage();
         }
      }
      elseif($data == "jobs" && $status == "waiting") {
         try {
            $jobs_F = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'F', $period, null);
            $jobs_S = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'S', $period, null);
            $jobs_m = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'm', $period, null);
            $jobs_M = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'M', $period, null);
            $jobs_s = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 's', $period, null);
            $jobs_j = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'j', $period, null);
            $jobs_c = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'c', $period, null);
            $jobs_d = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'd', $period, null);
            $jobs_t = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 't', $period, null);
            $jobs_p = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'p', $period, null);
            $jobs_q = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'q', $period, null);
            $jobs_C = $this->getJobModel()->getJobsByStatus($this->bsock, $jobname, 'C', $period, null);
            $result = array_merge(
               $jobs_F,$jobs_S,$jobs_m,$jobs_M,
               $jobs_s,$jobs_j,$jobs_c,$jobs_d,
               $jobs_t,$jobs_p,$jobs_q,$jobs_C
            );
         }
         catch(Exception $e) {
            echo $e->getMessage();
         }
      }
      elseif($data == "runjobs") {
         try {
            // Get the different kind of jobs and merge them. Jobs of the following types
            // cannot nor wanted to be run. M,V,R,U,I,C and S.
            $jobs_B = $this->getJobModel()->getJobsByType($this->bsock, 'B'); // Backup Job
            $jobs_D = $this->getJobModel()->getJobsByType($this->bsock, 'D'); // Admin Job
            $jobs_A = $this->getJobModel()->getJobsByType($this->bsock, 'A'); // Archive Job
            $jobs_c = $this->getJobModel()->getJobsByType($this->bsock, 'c'); // Copy Job
            $jobs_g = $this->getJobModel()->getJobsByType($this->bsock, 'g'); // Migration Job
            $jobs_O = $this->getJobModel()->getJobsByType($this->bsock, 'O'); // Always Incremental Consolidate Job
            $jobs_V = $this->getJobModel()->getJobsByType($this->bsock, 'V'); // Verify Job
            $result = array_merge(
               $jobs_B,$jobs_D,$jobs_A,$jobs_c,$jobs_g,$jobs_O,$jobs_V
            );
         }
         catch(Exception $e) {
            echo $e->getMessage();
         }
      }
      elseif($data == "details") {
         try {
            $result = $this->getJobModel()->getJob($this->bsock, $jobid);
         }
         catch(Exception $e) {
            echo $e->getMessage();
         }
      }
      elseif($data == "logs" && isset($jobid)) {
         try {
            $result = $this->getJobModel()->getJobLog($this->bsock, $jobid);
         }
         catch(Exception $e) {
            echo $e->getMessage();
         }
      }
      elseif($data == "jobmedia" && isset($jobid)) {
         try {
            $result = $this->getJobModel()->getJobMedia($this->bsock, $jobid);
         }
         catch(Exception $e) {
            echo $e->getMessage();
         }
      }

      try {
            $this->bsock->disconnect();
      }
      catch(Exception $e) {
         echo $e->getMessage();
      }

      $response = $this->getResponse();
      $response->getHeaders()->addHeaderLine('Content-Type', 'application/json');

      if(isset($result)) {
         $response->setContent(JSON::encode($result));
      }

      return $response;
   }

   public function getJobModel()
   {
      if(!$this->jobModel) {
         $sm = $this->getServiceLocator();
         $this->jobModel = $sm->get('Job\Model\JobModel');
      }
      return $this->jobModel;
   }

   public function getClientModel()
   {
      if(!$this->clientModel) {
         $sm = $this->getServiceLocator();
         $this->clientModel = $sm->get('Client\Model\ClientModel');
      }
      return $this->clientModel;
   }

   public function getStorageModel()
   {
      if(!$this->storageModel) {
         $sm = $this->getServiceLocator();
         $this->storageModel = $sm->get('Storage\Model\StorageModel');
      }
      return $this->storageModel;
   }

   public function getPoolModel()
   {
      if(!$this->poolModel) {
         $sm = $this->getServiceLocator();
         $this->poolModel = $sm->get('Pool\Model\PoolModel');
      }
      return $this->poolModel;
   }

   public function getFilesetModel()
   {
      if(!$this->filesetModel) {
         $sm = $this->getServiceLocator();
         $this->filesetModel = $sm->get('Fileset\Model\FilesetModel');
      }
      return $this->filesetModel;
   }

}
